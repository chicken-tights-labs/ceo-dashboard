#!/usr/bin/env python3
"""
CEO Dashboard - Live Kanban UI
A lightweight FastAPI app that serves real-time kanban board data

Two views:
  /              — CEO Dashboard exec view (DASH tasks only, table grouped by epic)
  /board         — Full kanban board (all tasks, all statuses) — dev/debug

Access via: https://hermes.chickentightslabs.com/ceo-dashboard/

Usage:
  python3 src/dashboard_server.py
"""
import sqlite3
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Scope
import jinja2

KANBAN_DB = "/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db"
TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

# Ensure directories exist
TEMPLATES_DIR.mkdir(exist_ok=True)
STATIC_DIR.mkdir(exist_ok=True)

# Raw jinja2 environment (avoids Starlette template cache cache-key issues with dicts)
_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
    auto_reload=True,
    autoescape=jinja2.select_autoescape(['html']),
)

app = FastAPI(title="CEO Dashboard", description="Live Kanban Board")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# CORS: explicit allowlist, no credentials (US-DASH-012).
#
# An origin is scheme + host + port; the /ceo-dashboard path is not part of it.
# The dashboard is read-only and its page and API share one origin, so this list
# only matters for other browser origins. Never combine "*" with credentials:
# Starlette would echo any Origin back, which allows every site.
# To add a hostname, add it here and update docs/environment.md (CORS gotcha).
ALLOWED_ORIGINS = [
    "https://hermes.chickentightslabs.com",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PathPrefixStripper(ASGIApp):
    """Strips the /ceo-dashboard prefix so routes work behind the Cloudflare Tunnel.

    The cloudflared tunnel forwards /ceo-dashboard* to this app preserving the
    full path. Without stripping, /ceo-dashboard/ would 404 because the app has
    no route at that path.
    """

    def __init__(self, app, prefix="/ceo-dashboard"):
        self.app = app
        self.prefix = prefix.rstrip("/")

    async def __call__(self, scope: Scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            if path.startswith(self.prefix):
                scope["path"] = path[len(self.prefix):] or "/"
                # Also fix the root_path so URL generation works
                if not scope["path"].startswith("/"):
                    scope["path"] = "/" + scope["path"]
        await self.app(scope, receive, send)


app.add_middleware(PathPrefixStripper, prefix="/ceo-dashboard")

# Status order for display.
#
# This MUST stay a superset of every status the kanban DB can hold. Hermes
# accepts: {"triage", "todo", "scheduled", "ready", "running", "blocked",
# "review", "done", "archived"} (hermes_cli/kanban_db.py VALID_STATUSES).
# "archived" is intentionally omitted — the board query filters it out.
STATUS_ORDER = ["ready", "review", "todo", "scheduled", "running", "triage", "blocked", "done"]
STATUS_COLORS = {
    "ready": "#6b7280",      # gray
    "review": "#a855f7",     # purple
    "todo": "#3b82f6",       # blue
    "scheduled": "#06b6d4",  # cyan
    "running": "#10b981",    # green
    "triage": "#f59e0b",     # amber
    "blocked": "#ef4444",    # red
    "done": "#22c55e",       # emerald
}
STATUS_LABELS = {
    "ready": "Queued",
    "review": "In Review",
    "todo": "Backlog",
    "scheduled": "Scheduled",
    "running": "In Progress",
    "triage": "Triage",
    "blocked": "Blocked",
    "done": "Complete",
}

# Fallback for a status the dashboard has never seen. Rendering an unknown
# status beats raising KeyError and taking the whole board down.
UNKNOWN_STATUS_COLOR = "#9ca3af"


def _status_sort_key(status: str) -> int:
    """Known statuses first in STATUS_ORDER; unknown ones last."""
    try:
        return STATUS_ORDER.index(status)
    except ValueError:
        return len(STATUS_ORDER)


# ---------------------------------------------------------------------------
# Full board state (all tasks, all statuses) — used by /board and /api/state
# ---------------------------------------------------------------------------

def get_board_state():
    """Query kanban DB for active tasks grouped by status.

    Tolerates any status value: a card whose status is not in STATUS_ORDER is
    still rendered (in its own column) rather than raising KeyError.
    """
    conn = sqlite3.connect(KANBAN_DB, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    tasks = conn.execute(
        "SELECT id, title, status, assignee, body, created_at, priority "
        "FROM tasks WHERE status != 'archived' ORDER BY priority DESC, created_at DESC"
    ).fetchall()
    conn.close()

    # Seed the known columns, then add any extra status actually present.
    statuses = list(STATUS_ORDER)
    for t in tasks:
        if t["status"] and t["status"] not in statuses:
            statuses.append(t["status"])
    statuses.sort(key=_status_sort_key)

    board = {status: [] for status in statuses}

    for t in tasks:
        short_id = t["id"][-6:] if t["id"] else ""
        assignee_text = t["assignee"] or "-"
        platform = "-"
        model = "-"
        if assignee_text:
            parts = assignee_text.split()
            for p in parts:
                if "@platform:" in p:
                    platform = p.replace("@platform:", "").upper()
                elif "@used-model:" in p:
                    model = p.replace("@used-model:", "").replace("-", " ")

        board[t["status"]].append({
            "id": short_id,
            "full_id": t["id"],
            "title": t["title"] or "Untitled",
            "body": (t["body"] or "")[:200],
            "assignee": assignee_text,
            "platform": platform,
            "model": model,
            "created": datetime.utcfromtimestamp(t["created_at"]).strftime("%b %d"),
            "priority": t["priority"] or 0,
            "agent_assigned": platform != "-",
        })

    return board


def get_summary_stats(board):
    """Calculate summary stats from board state.

    Iterates the board's own keys rather than STATUS_ORDER so a card in an
    unexpected status still counts toward the total.
    """
    return {
        "total": sum(len(v) for v in board.values()),
        "queued": len(board.get("ready", [])),
        "review": len(board.get("review", [])),
        "in_progress": len(board.get("running", [])),
        "blocked": len(board.get("blocked", [])),
        "complete": len(board.get("done", [])),
    }


# ---------------------------------------------------------------------------
# CEO Dashboard exec view (DASH tasks only, grouped by epic)
# ---------------------------------------------------------------------------

# A DASH epic is a task whose title matches one of these patterns.
# EPIC-05 = CEO Dashboard Development; EPIC-06 = Notifications (split from EPIC-05).
# Also match "CEO Dashboard" generically so new epics with that phrase are caught.
DASH_EPIC_TITLE_PATTERNS = [
    "EPIC-05",
    "EPIC-06",
]
DASH_EPIC_TITLE_CONTAINS = [
    "ceo dashboard",  # case-insensitive substring
]


def _is_dash_title(title: str) -> bool:
    """Returns True if a task title marks it as a DASH (CEO Dashboard) task.

    Matches:
      - 'US-DASH-XXX'  (e.g. 'US-DASH-001: Static Kanban Mirror Export')
      - 'CEO Dashboard' in the title (e.g. 'EPIC-05: CEO Dashboard Development')
    Does NOT match:
      - 'US-D001' (documentation tasks — note these are US-D, not US-DASH)
      - 'US-T001' (Trainer), 'US-F001' (Finance)
    """
    lower = title.lower()
    if "us-dash" in lower:
        return True
    if "ceo dashboard" in lower:
        return True
    return False


def _is_dash_epic_title(title: str) -> bool:
    """Returns True if a task title marks it as a DASH epic.

    A DASH epic is an EPIC task related to the CEO Dashboard. Must start with
    'EPIC-' AND match one of the known DASH epic prefixes OR contain 'CEO Dashboard'.
    This prevents user stories like 'US-DASH-006: ... for CEO Dashboard' from
    being mistakenly treated as epics.
    """
    if not title.startswith("EPIC-"):
        return False
    for prefix in DASH_EPIC_TITLE_PATTERNS:  # ["EPIC-05", "EPIC-06"]
        if title.startswith(prefix):
            return True
    # Catch-all: any EPIC with 'CEO Dashboard' in title (future-proofing for
    # EPIC-07, EPIC-08, etc. that relate to the dashboard)
    if "ceo dashboard" in title.lower():
        return True
    return False


def _is_dash_task(row: sqlite3.Row, epic_ids: set[str], child_to_parent: dict[str, str]) -> tuple[bool, str | None]:
    """Determine whether a task row belongs to the CEO Dashboard (DASH) scope.

    Returns (is_dash, parent_epic_id) where parent_epic_id is the ID of the
    DASH epic this task belongs to, or None if unlinked.

    A task is DASH if ANY of:
      1. It is a child of a DASH epic (via task_links)
      2. Its title contains 'US-DASH' or 'CEO Dashboard' (case-insensitive)
      3. Its workspace_path contains 'ceo-dashboard' (auto-generated tickets
         from the ceo-dashboard repo's Gherkin requirements)
      4. It IS a DASH epic itself
    """
    task_id = row["id"]
    title = row["title"] or ""
    workspace_path = row["workspace_path"] or ""

    # Criterion 4: it's a DASH epic itself
    if task_id in epic_ids:
        return True, None  # epics are their own group

    # Criterion 1: child of a DASH epic
    parent = child_to_parent.get(task_id)
    if parent and parent in epic_ids:
        return True, parent

    # Criterion 2: title-based
    if _is_dash_title(title):
        return True, parent  # parent may be None if unlinked

    # Criterion 3: workspace_path from auto-ticket creator
    if "ceo-dashboard" in workspace_path:
        return True, parent

    return False, None


def _parse_assignee(assignee_text: str) -> dict:
    """Parse the assignee field into platform, model, and is_ai flag.

    @platform:cursor in the assignee (any position) means the task was assigned
    to an AI agent (Cursor). Absence means it's for human review.
    """
    platform = "-"
    model = "-"
    is_ai = False

    if assignee_text:
        parts = assignee_text.split()
        for p in parts:
            if "@platform:" in p:
                platform = p.replace("@platform:", "").upper()
                is_ai = True
            elif "@used-model:" in p:
                model = p.replace("@used-model:", "").replace("-", " ")

    # Also check bracketed form: "default [@platform:cursor]"
    if not is_ai and "[@platform:" in assignee_text:
        is_ai = True
        platform = "CURSOR"

    return {"platform": platform, "model": model, "is_ai": is_ai}


def get_dash_epics():
    """Return {epic_id: epic_title} for all DASH epic tasks in the kanban DB."""
    conn = sqlite3.connect(KANBAN_DB, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, title FROM tasks WHERE status != 'archived'"
    ).fetchall()
    conn.close()

    epics = {}
    for r in rows:
        title = r["title"] or ""
        if _is_dash_epic_title(title):
            epics[r["id"]] = title
    return epics


def get_ceo_dashboard_state():
    """Query kanban DB for DASH-only tasks, grouped by epic.

    Separates CEO Dashboard tasks (US-DASH-*, EPIC-05, EPIC-06, and auto-tickets
    from the ceo-dashboard repo) from Salesforce headless-dev tasks.

    Returns:
        {
            "epics": {
                "EPIC-05: CEO Dashboard Development": {
                    "id": "t_dash_01",
                    "tasks": [ {task dict}, ... ],
                },
                "Other DASH Tasks": {
                    "id": None,
                    "tasks": [ {task dict}, ... ],
                },
            },
            "stats": { ... },
        }
    """
    conn = sqlite3.connect(KANBAN_DB, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row

    # 1. Find DASH epic tasks
    epic_ids = set(get_dash_epics().keys())
    epic_titles = get_dash_epics()

    # 2. Build child -> parent map from task_links
    child_to_parent = {}
    for row in conn.execute("SELECT parent_id, child_id FROM task_links").fetchall():
        child_to_parent[row["child_id"]] = row["parent_id"]

    # 3. Query all non-archived tasks (need workspace_path for auto-ticket detection)
    rows = conn.execute(
        "SELECT id, title, status, assignee, body, created_at, priority, "
        "workspace_path FROM tasks WHERE status != 'archived' "
        "ORDER BY priority DESC, created_at DESC"
    ).fetchall()
    conn.close()

    # 4. Filter to DASH tasks and group by epic
    epics: dict[str, dict] = {}
    other_tasks = []

    for row in rows:
        is_dash, parent_epic_id = _is_dash_task(row, epic_ids, child_to_parent)
        if not is_dash:
            continue

        assignee_text = row["assignee"] or "-"
        parsed = _parse_assignee(assignee_text)

        short_id = row["id"][-6:] if row["id"] else ""
        task = {
            "id": short_id,
            "full_id": row["id"],
            "title": row["title"] or "Untitled",
            "body": (row["body"] or "")[:200],
            "assignee": assignee_text,
            "platform": parsed["platform"],
            "model": parsed["model"],
            "is_ai": parsed["is_ai"],
            "status": row["status"] or "-",
            "created": datetime.utcfromtimestamp(row["created_at"]).strftime("%b %d"),
            "priority": row["priority"] or 0,
        }

        # Group under epic
        if row["id"] in epic_ids:
            # It's a DASH epic — create the group header, but don't add the
            # epic itself as a task row. Its children will appear below it.
            epic_title = row["title"] or "Untitled"
            if epic_title not in epics:
                epics[epic_title] = {"id": row["id"], "tasks": []}
        elif parent_epic_id and parent_epic_id in epic_ids:
            epic_title = epic_titles[parent_epic_id]
            if epic_title not in epics:
                epics[epic_title] = {"id": parent_epic_id, "tasks": []}
            epics[epic_title]["tasks"].append(task)
        else:
            other_tasks.append(task)

    if other_tasks:
        epics["Other DASH Tasks"] = {"id": None, "tasks": other_tasks}

    # 5. Stats
    all_dash_tasks = [t for e in epics.values() for t in e["tasks"]]
    status_counts = {}
    for t in all_dash_tasks:
        s = t["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    stats = {
        "total": len(all_dash_tasks),
        "ai_assigned": sum(1 for t in all_dash_tasks if t["is_ai"]),
        "human_review": sum(1 for t in all_dash_tasks if not t["is_ai"]),
        "queued": status_counts.get("ready", 0),
        "in_progress": status_counts.get("running", 0),
        "review": status_counts.get("review", 0),
        "backlog": status_counts.get("todo", 0),
        "blocked": status_counts.get("blocked", 0),
        "complete": status_counts.get("done", 0),
    }

    return {"epics": epics, "stats": stats}


def get_ceo_summary_stats(ceo_state):
    """Alias for compatibility; delegate to state's embedded stats."""
    return ceo_state.get("stats", {})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def ceo_dashboard_root(request: Request):
    """CEO Dashboard exec view: color-coded table of DASH tasks grouped by epic."""
    ceo_state = get_ceo_dashboard_state()
    stats = ceo_state["stats"]

    template = _env.get_template("ceo_dashboard.html")
    return template.render(
        request=request,
        epics=ceo_state["epics"],
        stats=stats,
        status_labels=STATUS_LABELS,
        status_colors=STATUS_COLORS,
        unknown_status_color=UNKNOWN_STATUS_COLOR,
        last_updated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.get("/board", response_class=HTMLResponse)
async def kanban_board(request: Request):
    """Full kanban board view: all tasks grouped by status (dev/debug)."""
    board = get_board_state()
    stats = get_summary_stats(board)

    template = _env.get_template("dashboard.html")
    return template.render(
        request=request,
        board=board,
        stats=stats,
        status_labels=STATUS_LABELS,
        status_colors=STATUS_COLORS,
        status_order=list(board.keys()),
        unknown_status_color=UNKNOWN_STATUS_COLOR,
        last_updated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.get("/api/state")
async def api_state():
    """JSON endpoint for full kanban board state (backward compatible)."""
    board = get_board_state()
    stats = get_summary_stats(board)
    return {"board": board, "stats": stats}


@app.get("/api/ceo-state")
async def api_ceo_state():
    """JSON endpoint for CEO Dashboard DASH-only state."""
    return get_ceo_dashboard_state()


@app.get("/health")
async def health():
    """Health check endpoint for monitoring."""
    return {"status": "ok", "service": "ceo-dashboard"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)

#!/usr/bin/env python3
"""
CEO Dashboard - Live Kanban UI
A lightweight FastAPI app that serves real-time kanban board data
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

# CORS headers for browser access through Cloudflare Tunnel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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


@app.get("/", response_class=HTMLResponse)
async def dashboard_root(request: Request):
    """Main dashboard page"""
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
    """JSON endpoint for kanban state"""
    board = get_board_state()
    stats = get_summary_stats(board)
    return {"board": board, "stats": stats}




@app.get("/health")
async def health():
    """Health check endpoint for monitoring"""
    return {"status": "ok", "service": "ceo-dashboard"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)

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

# Status order for display
STATUS_ORDER = ["ready", "todo", "running", "blocked", "done"]
STATUS_COLORS = {
    "ready": "#6b7280",     # gray
    "todo": "#3b82f6",      # blue
    "running": "#10b981",   # green
    "blocked": "#ef4444",   # red
    "done": "#22c55e",      # emerald
}
STATUS_LABELS = {
    "ready": "Queued",
    "todo": "Backlog",
    "running": "In Progress",
    "blocked": "Blocked",
    "done": "Complete",
}


def get_board_state():
    """Query kanban DB for active tasks grouped by status"""
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row
    tasks = conn.execute(
        "SELECT id, title, status, assignee, body, created_at, priority "
        "FROM tasks WHERE status != 'archived' ORDER BY priority DESC, created_at DESC"
    ).fetchall()
    conn.close()

    board = {status: [] for status in STATUS_ORDER}

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
    """Calculate summary stats from board state"""
    return {
        "total": sum(len(board[s]) for s in STATUS_ORDER),
        "queued": len(board["ready"]),
        "in_progress": len(board["running"]),
        "blocked": len(board["blocked"]),
        "complete": len(board["done"]),
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
        last_updated=datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
    )


@app.get("/api/state")
async def api_state():
    """JSON endpoint for kanban state"""
    board = get_board_state()
    stats = get_summary_stats(board)
    return {"board": board, "stats": stats}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8081)

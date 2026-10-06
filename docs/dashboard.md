# CEO Dashboard - Live Kanban UI

## Files
- `src/dashboard_server.py` — FastAPI server (port 8081)
- `src/templates/dashboard.html` — Full kanban board view (all tasks, all statuses)
- `src/templates/ceo_dashboard.html` — CEO Dashboard exec view (DASH tasks only)
- `src/static/dashboard.css` — Dashboard styles

## Routes

| Route | Template | Scope | Description |
|---|---|---|---|
| `/` | `ceo_dashboard.html` | DASH only | Color-coded table of CEO Dashboard tasks, grouped by epic. AI=green, Human=blue. Auto-refresh 60s. |
| `/board` | `dashboard.html` | All tasks | Full kanban board (all 41 tasks, all statuses). Dev/debug view. |
| `/api/state` | JSON | All tasks | Full board state (backward compatible). |
| `/api/ceo-state` | JSON | DASH only | Executive summary: DASH epics + tasks + stats. |
| `/health` | JSON | — | Health check endpoint. |

## Running
```bash
pip install fastapi jinja2 uvicorn
uvicorn src.dashboard_server:app --host 127.0.0.1 --port 8081
```

Or via systemd:
```bash
sudo systemctl restart ceo-dashboard
```

## DASH Task Identification

The CEO Dashboard exec view filters to DASH tasks only (separating them from
Salesforce headless-dev tasks like US-T*, US-F*, US-D*). A task is identified
as DASH if ANY of:

1. It is a child of a DASH epic (EPIC-05, EPIC-06) via `task_links`
2. Its title contains `US-DASH` (case-insensitive)
3. Its title contains `CEO Dashboard` (case-insensitive)
4. Its `workspace_path` contains `ceo-dashboard` (auto-tickets from the repo)
5. It IS a DASH epic (EPIC-05/EPIC-06)

Epic detection requires the `EPIC-` prefix to avoid misclassifying
`US-DASH-006: ... for CEO Dashboard` as an epic.

## NGINX Route
```nginx
location /ceo-dashboard/ {
    proxy_pass http://127.0.0.1:8081/;
}
```

## VM Facts
- Service: `ceo-dashboard` (systemd), port 8081, binds 127.0.0.1
- Service file: `/etc/systemd/system/ceo-dashboard.service`
- Repo: `/home/maria_robbins/sf-project/ceo-dashboard`
- Python: `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python`
- DB: `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db`
- Health: `curl -s http://127.0.0.1:8081/health`
- Exec view: `curl -s http://127.0.0.1:8081/`
- Kanban board: `curl -s http://127.0.0.1:8081/board`

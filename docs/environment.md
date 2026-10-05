# CEO Dashboard — Environment Facts

> Facts about the VM that Cursor cannot see. Hermes maintains this; update when things change.

## Services

| Service | Port | Systemd Unit | Health Check |
|---|---|---|---|
| CEO Dashboard (FastAPI/uvicorn) | 8081 | `ceo-dashboard` | `curl -s http://127.0.0.1:8081/api/state | jq .` |
| NGINX (CF Tunnel origin) | 80 | `nginx` | `systemctl is-active nginx` |
| Cloudflare Tunnel | — | `cloudflared` | `cloudflared tunnel list` |

## Paths

| Resource | Path |
|---|---|
| Repo clone (VM working copy) | `/home/maria_robbins/sf-project/ceo-dashboard` |
| Systemd service file | `/etc/systemd/system/ceo-dashboard.service` |
| Python venv | `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python` |
| Dashboard app logs | `/tmp/dashboard-server.log` **and** `journalctl -u ceo-dashboard` |
| Kanban DB | `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db` |
| Auto-ticket state file | `/home/maria_robbins/.hermes/scripts/auto-ticket-state.json` |
| NGINX config | `/etc/nginx/sites-available/ceo-dashboard` |

## Deploy & Verify Commands

```bash
# After PR merges to main:
cd /home/maria_robbins/sf-project/ceo-dashboard
git pull origin main
sudo systemctl restart ceo-dashboard
sleep 2
curl -s http://127.0.0.1:8081/api/state | jq .
```

A healthy `/api/state` returns JSON with `board` (ready/todo/running/blocked/done arrays) and `stats` object:

```json
{
  "board": { "ready": [...], "todo": [...], "running": [], "blocked": [], "done": [...] },
  "stats": { "total": 41, "queued": 15, "in_progress": 0, "blocked": 0, "complete": 3 }
}
```

## Python Paths Per Component

| Component | Python | Why |
|---|---|---|
| systemd (`ceo-dashboard.service`) | venv: `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python` | App uses FastAPI/uvicorn which need venv packages |
| cron (`auto_ticket_creator.sh`) | system `python3` | Script uses only stdlib (hashlib, json, re, sqlite3, uuid) |
| cron (`kanban_mirror.sh`) | system `python3` | Imports hermes kanban tools via PYTHONPATH |
| Manual dev runs | venv for app, `python3` for scripts | Match each component's needs |

## Path Prefix Handling (Two Layers)

1. **NGINX** — `location /ceo-dashboard { proxy_pass http://127.0.0.1:8081/; }` — the trailing `/` in proxy_pass strips `/ceo-dashboard` before forwarding to the app.
2. **App** — `PathPrefixStripper` middleware in `dashboard_server.py` also strips `/ceo-dashboard` if present.

When behind NGINX, layer 2 is redundant. Both must agree on which one strips — currently both do. If someone accesses the app directly on port 8081 with a prefixed path, only layer 2 applies.

## NGINX Config

```nginx
server {
    listen 80;
    server_name hermes.chickentightslabs.com;

    location /ceo-dashboard {
        proxy_pass http://127.0.0.1:8081/;
        proxy_set_header Host hermes.chickentightslabs.com;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
    }

    location / {
        proxy_pass http://127.0.0.1:8090;
    }
}
```

## Auto-Ticket State File

- **Location**: `/home/maria_robbins/.hermes/scripts/auto-ticket-state.json`
- **Format**: `{"processed": {"<sha256_hash>": "<task_id>", ...}}`
- **Dedup key**: SHA256 of `scenario_name + gherkin_body` (first 16 hex chars), computed by `scenario_hash()` in the script
- The key is **not** the scenario `@cursor` name — it's a content hash. Renaming a scenario still produces a new hash, so a renamed scenario creates a new ticket.

## No /health Endpoint

The app has only two routes: `/` (HTML dashboard) and `/api/state` (JSON). `curl http://127.0.0.1:8081/health` returns **404**. Use `/api/state` for health checks until a `/health` endpoint is added (separate story, out of scope here).

## Known Gotchas

1. **python3-on-venv mismatch (the real bug)**: Cron scripts run `python3 script.py` (system Python) — NOT the venv binary. Running `venv/bin/python` from cron for stdlib-only scripts causes issues because the venv binary looks for packages in `__pycache__` paths that don't exist in the cron environment. Fix: use `python3 script.py` with `PYTHONPATH=/home/maria_robbins/.hermes/hermes-agent` for scripts that import hermes modules. Only the FastAPI/uvicorn app needs the venv.
2. **Dual prefix stripping**: NGINX and the app both strip `/ceo-dashboard`. Redundant but harmless behind NGINX. Documented here to avoid confusion if someone changes one layer.
3. **No /health endpoint**: Use `curl -s http://127.0.0.1:8081/api/state | jq .` instead.
4. **Kanban DB board name**: Path contains `salesforce-headless-dev`. If board name changes, update this file and `tasks/architecture.md`.
5. **Auto-ticket creator reads only requirements.md**: The script scans `tasks/requirements.md` for `@cursor` scenarios. It does **not** read GitHub issues. To auto-generate kanban tickets, write Gherkin in requirements.md.
6. **Logs go to two places**: systemd writes to `/tmp/dashboard-server.log` AND to journald (`journalctl -u ceo-dashboard --no-pager`). The `/tmp` file is not rotated — watch for disk growth.

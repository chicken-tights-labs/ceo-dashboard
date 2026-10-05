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
| cron (`kanban_mirror.sh`) | system `python3` | Script uses only stdlib (sqlite3, os, time, datetime, pathlib); it does not import hermes modules. `PYTHONPATH` is exported by the wrapper but not needed by the current script. **Calls the repo's `src/kanban_mirror.py`, not `~/.hermes/tools/` — see "Cron Script-to-Python Mapping" below. |
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

## Health Endpoint

The app has three routes: `/` (HTML dashboard), `/api/state` (JSON), and `/health` (added in US-DASH-006, returns `{"status": "ok", "service": "ceo-dashboard"}`). Use `/health` for liveness checks and `/api/state` for board data.

## Known Gotchas

1. **Never pass the venv binary to `python3` (the real bug)**: `kanban_mirror.sh` used to run `python3 /home/maria_robbins/.hermes/hermes-agent/venv/bin/python /home/maria_robbins/.hermes/tools/kanban_mirror.py`. That tells system `python3` to execute the venv `python` *binary* as if it were a script, which fails immediately with a `SyntaxError`. Fixed in `f1b363f`. Rule: run a script with **either** `python3 script.py` **or** `/path/to/venv/bin/python script.py` — never both in one command. Cron scripts use system `python3`; only the FastAPI/uvicorn app (systemd) needs the venv.

2. **Dual prefix stripping**: NGINX and the app both strip `/ceo-dashboard`. Redundant but harmless behind NGINX. Documented here to avoid confusion if someone changes one layer.
3. **No /health endpoint**: Use `curl -s http://127.0.0.1:8081/api/state | jq .` instead.
4. **Kanban DB board name**: Path contains `salesforce-headless-dev`. If board name changes, update this file and `tasks/architecture.md`.
5. **Auto-ticket creator reads only requirements.md**: The script scans `tasks/requirements.md` for `@cursor` scenarios. It does **not** read GitHub issues. To auto-generate kanban tickets, write Gherkin in requirements.md.
6. **Logs go to two places**: systemd writes to `/tmp/dashboard-server.log` AND to journald (`journalctl -u ceo-dashboard --no-pager`). The `/tmp` file is not rotated — watch for disk growth.
7. **Repo-managed cron scripts must be executable and called by repo path**: The crontab entries for `kanban_mirror.sh` and `auto_ticket_creator.sh` point directly at `/home/maria_robbins/sf-project/ceo-dashboard/scripts/`. There are no copies in `~/.hermes/scripts/` to keep in sync. The scripts are committed with the executable bit; if a cron run fails with "Permission denied", run `chmod +x scripts/*.sh` in the clone. See "Cron Script-to-Python Mapping" below.

8. **Dashboard status list must cover every kanban status**: `src/dashboard_server.py` builds its board columns from `STATUS_ORDER` plus any status found in the DB. Hermes' kanban accepts nine statuses (`triage`, `todo`, `scheduled`, `ready`, `running`, `blocked`, `review`, `done`, `archived`). A card in a status with no column previously raised `KeyError` and returned **HTTP 500 for the entire board**, not just that card — `github_sync.py` moving a card to `review` would have triggered it. Keep `STATUS_ORDER`/`STATUS_COLORS`/`STATUS_LABELS` a superset of the eight displayed statuses; unknown statuses now degrade gracefully. Regression tests: `tests/test_dashboard_status.py`. Run the suite with `python -m unittest discover -s tests -v` (venv Python).

## Cron Script-to-Python Mapping

Single source of truth for which file each cron entry executes. Prevents VM-to-repo drift.

| Cron Entry | Shell Script (repo path, called directly by cron) | Python Script (repo path) | Python |
|---|---|---|---|
| `0 9,21 * * *` | `/home/maria_robbins/sf-project/ceo-dashboard/scripts/kanban_mirror.sh` | `src/kanban_mirror.py` | system `python3` (stdlib only) |
| `3 * * * *` | `/home/maria_robbins/sf-project/ceo-dashboard/scripts/auto_ticket_creator.sh` | `scripts/auto_ticket_creator.py` | system `python3` (stdlib only) |
| `*/15 * * * *` | `/home/maria_robbins/sf-project/ceo-dashboard/scripts/github_sync.sh` | `scripts/github_sync.py` | system `python3` (stdlib only; needs authenticated `gh` on PATH) |
| `0 23 * * *` | `~/.hermes/scripts/journal_obsidian.py` | N/A (inline) | system `python3` |
| `0 * * * *` | `~/scripts/sync-obsidian-vault.sh` | N/A (rclone) | N/A |
| `0 3 1,4,7,10 *` | `~/.hermes/scripts/hermes-backup.sh` | N/A | N/A |
| `0 3 1 *` | `~/.hermes/scripts/security-audit.sh` | N/A | N/A |
| `55 10 * * *` (PAUSED) | `~/.hermes/skills/.../researchrover_daily.py` | N/A | N/A |

**Rule**: For the two repo-managed cron jobs above, `git pull origin main` on the VM is the only deploy step. Do not copy these scripts anywhere. The other rows (journal, backup, security audit, vault sync) are not in the repo and are unchanged.

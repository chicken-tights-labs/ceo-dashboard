# Architecture Notes

## Overview
The CEO Dashboard operates as a three-layer system:

1. **Data Layer**: Reads from Hermes Kanban SQLite DB
   - Path: `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db`
   - Query pattern: SELECT tasks by status, group by status/assignee
   - Connections set a SQLite busy timeout to handle concurrent access from cron jobs:
     `src/dashboard_server.py` and `src/kanban_mirror.py` use 30000 ms
     (`sqlite3.connect(..., timeout=30)` + `PRAGMA busy_timeout = 30000`);
     `scripts/auto_ticket_creator.py` uses 5000 ms.
   - Known gap: the "Recently Added" query in `src/kanban_mirror.py` opens a second
     connection with no timeout (tracked for follow-up).

2. **Service Layer**: FastAPI micro-service on port 8081
   - Endpoints:
     - `/` → HTML dashboard page (`dashboard_root`)
     - `/api/state` → **JSON** endpoint with board state and stats (`api_state`)
   - `PathPrefixStripper` middleware strips `/ceo-dashboard` prefix for direct access
   - Binds to `127.0.0.1` only (not exposed directly)

3. **Presentation Layer**:
   - HTML template with JavaScript polling
   - Served behind Cloudflare Tunnel with BYPASS policy for laptop IP
   - Accessible at: hermes.chickentightslabs.com/ceo-dashboard/

## Routing & Prefix Stripping

**Two layers strip the prefix:**

1. **NGINX** (`location /ceo-dashboard { proxy_pass http://127.0.0.1:8081/; }`) — trailing `/` in proxy_pass strips `/ceo-dashboard` before forwarding to the app.
2. **App** (`PathPrefixStripper` middleware in `dashboard_server.py`) — `prefix="/ceo-dashboard"`, strips the prefix if present in the raw path.

When behind NGINX, the app's stripper is redundant (NGINX already stripped it). Both must agree on which strips — currently both do.

## CORS
The app sets `allow_origins=["*"]` combined with `allow_credentials=True`. This is a known issue and should be tightened to specific origins. It is not yet tracked as its own story; file one before changing it.

## Deployment Flow
1. Repo lives at `/home/maria_robbins/sf-project/ceo-dashboard`
2. Changes pushed to GitHub: `chicken-tights-labs/ceo-dashboard`
3. CI runs on PR: Python syntax check + shell lint (must pass before merge)
4. After merge: `git pull origin main` → `sudo systemctl restart ceo-dashboard` → verify with `curl -s http://127.0.0.1:8081/api/state | jq .`
5. Systemd manages the process with `Restart=always`, `RestartSec=5`

## Logs
- App output goes to `/tmp/dashboard-server.log` (systemd `StandardOutput=append`)
- Also available via journald: `journalctl -u ceo-dashboard --no-pager`
- Cron job logs: `kanban_mirror.sh` → `/home/maria_robbins/logs/kanban-mirror.log`, `auto_ticket_creator.sh` → `/home/maria_robbins/logs/auto-ticket.log`

## Security Notes
- Service binds to `127.0.0.1:8081` only (not exposed directly on the network)
- NGINX listens on port 80 and proxies to the app
- Cloudflare Tunnel enforces BYPASS policy for your IP
- No authentication layer yet (will add if needed)
- `/tmp/dashboard-server.log` is not log-rotated — monitor for disk growth

## Known Gotchas
- **No `/health` endpoint**: Use `curl -s http://127.0.0.1:8081/api/state | jq .` for health checks
- **Cron uses system python3**: Not the venv binary. Scripts are stdlib-only; only the FastAPI app uses the venv.
- **Dual prefix stripping**: Both NGINX and the app strip `/ceo-dashboard`. Redundant but harmless behind NGINX.

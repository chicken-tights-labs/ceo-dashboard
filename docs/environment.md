# CEO Dashboard — Environment Facts

> Facts about the VM that Cursor cannot see. Hermes maintains this; update when things change.

## Services

| Service | Port | Systemd Unit | Health Check |
|---|---|---|---|
| CEO Dashboard | 8081 | `ceo-dashboard` | `curl -s http://127.0.0.1:8081/api/state \| jq .` |
| NGINX (CF Tunnel origin) | 80 | `nginx` | `curl -s http://127.0.0.1:8081/health` |
| Cloudflare Tunnel | — | `cloudflared` | `cloudflared tunnel list` |

## Paths

| Resource | Path |
|---|---|
| Repo clone (VM working copy) | `/home/maria_robbins/sf-project/ceo-dashboard` |
| Systemd service file | `/etc/systemd/system/ceo-dashboard.service` |
| Python venv | `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python` |
| Dashboard logs | `/tmp/dashboard-server.log` |
| Kanban DB | `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db` |

## Deploy & Verify Commands

```bash
# After PR merges to main:
cd /home/maria_robbins/sf-project/ceo-dashboard
git pull origin main
sudo systemctl restart ceo-dashboard
sleep 2
curl -s http://127.0.0.1:8081/api/state | jq .
```

A healthy `/api/state` returns JSON with active task counts and no error field.

## Known Gotchas

1. **python3-on-venv binary mistake**: When restarting the service, never invoke `python3` directly — always use the venv at `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python`. Using system `python3` without venv packages causes `ModuleNotFoundError`.
2. **Dashboard origin mismatch**: The dashboard binds to `127.0.0.1:8081`. NGINX proxies `/ceo-dashboard/` → `http://127.0.0.1:8081/` with path prefix stripping. Do not change this without updating the NGINX config.
3. **Kanban DB path**: The DB path contains `dev` in the board name (`salesforce-headless-dev`). If the board name changes, update `tasks/architecture.md` and this file.
4. **CF Tunnel route**: The tunnel route is `hermes.chickentightslabs.com/ceo-dashboard/`. Do not add a trailing path segment in the CF config or it will 404.
5. **Auto-ticket creator cron**: Runs hourly at minute 3. State file: `auto-ticket-state.json` in the repo root. Deduplication key is the Gherkin `@cursor` scenario name.

## NGINX Config

The NGINX server block proxies to the dashboard:

```nginx
location /ceo-dashboard/ {
    proxy_pass http://127.0.0.1:8081/;
}
```

This strips the `/ceo-dashboard` prefix — the FastAPI app must NOT expect it.

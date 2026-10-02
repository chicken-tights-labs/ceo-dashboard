# Architecture Notes

## Overview
The CEO Dashboard operates as a three-layer system:

1. **Data Layer**: Reads from Hermes Kanban SQLite DB
   - Path: `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db`
   - Query pattern: SELECT tasks by status, group by epic/assignee

2. **Service Layer**: FastAPI micro-service on port 8191
   - Endpoints:
     - `/` → HTML dashboard page
     - `/api/data` → Plain text ASCII dashboard
   - Auto-refreshes every 60 seconds

3. **Presentation Layer**: 
   - HTML template with JavaScript polling
   - Served behind Cloudflare Tunnel with Bypass policy
   - Accessible at: hermes.chickentightslabs.com/ceo-dashboard/

## Deployment Flow
1. Repo lives at `/home/maria_robbins/sf-project/ceo-dashboard`
2. Changes pushed to GitHub: `chicken-tights-labs/ceo-dashboard`
3. No CI/CD yet — manual redeploy via:
   ```bash
   # On VM:
   cd ~/.hermes/tools && python3 ceo_dashboard_fastapi.py &
   ```

## Security Notes
- Service binds to 127.0.0.1 only (not exposed directly)
- Cloudflare Tunnel enforces BYPASS policy for your IP
- No authentication layer yet (will add if needed)

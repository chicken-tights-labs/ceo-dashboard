# Product Backlog - CEO Dashboard

## Priority 1: Core Infrastructure
- [x] Set up GitHub repo (`chicken-tights-labs/ceo-dashboard`)
- [ ] Create FastAPI service to serve dashboard UI
- [ ] Wire up Cloudflare Tunnel route (`hermes.chickentightslabs.com/ceo-dashboard/`)
- [ ] Implement kanban SQLite DB reader

## Priority 2: Kanban Mirror
- [ ] Hourly cron job exports board state to `tasks/backlog.md`
- [ ] Format as markdown table with status/assignee columns
- [ ] Auto-tag with `@needs-review` where applicable

## Priority 3: Auto-Ticket Creator ✅
- [x] Monitor Obsidian requirements folder for new Gherkin files
- [x] Parse scenarios tagged with `@cursor`
- [x] Generate GitHub issue + kanban ticket pair
- [x] Assign to Cursor via `@platform:cursor` label
- [x] Script: `scripts/auto_ticket_creator.py`
- [x] Cron: hourly at minute 3
- [x] State file: `auto-ticket-state.json` (deduplication)

## Priority 4: Live Dashboard UI
- [ ] Responsive HTML table showing active tickets
- [ ] Group by epic with color-coded statuses
- [ ] Show AI vs human assignee distinction (green/blue)
- [ ] Auto-refresh every 60 seconds

## Priority 5: GitHub Sync
- [ ] Link GitHub issue numbers to kanban task IDs
- [ ] Auto-update kanban when PR is opened/merged
- [ ] Add "Deploy" button that pushes to scratch org

## Future Enhancements
- Daily digest sent to Telegram/Discord
- Slack-style threaded comments on tickets
- Time tracking integration (Clockify or Harvest)

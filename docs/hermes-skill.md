# CEO Dashboard Workflow Skill (Versioned Copy)

> This is a versioned copy of the Hermes skill `ceo-dashboard-workflow` that lives at
> `~/.hermes/skills/ceo-dashboard-workflow/SKILL.md`. Keeping a copy in the repo
> allows Cursor and other agents to read the exact rules Hermes enforces.

## Trigger

Activates when:
- Working in repo clone at `/home/maria_robbins/sf-project/ceo-dashboard/`
- Task mentions ceo-dashboard, CEO Dashboard, dashboard_server.py, or kanban_mirror.py
- Task involves the CEO Dashboard systemd service (port 8081)

## Hard Rules (Enforce Always)

1. **NO direct pushes to main.** Must open a branch (`feature/US-DASH-00N-short-name`) and create a PR. For production fixes, use a `hotfix/` branch and expedited PR.
2. **NEVER implement stories assigned to `@platform:cursor`.** These are Cursor's terminal lane — they wait for manual pickup in Cursor IDE.
3. **NEVER close a GitHub issue or mark a kanban card `done` before PR merges AND `git pull` + `systemctl restart ceo-dashboard` + health check.**
4. **After merge:** `git pull origin main` → `sudo systemctl restart ceo-dashboard` → verify: `curl -s http://127.0.0.1:8081/api/state | jq .`
5. **Branch naming:** `feature/US-DASH-00N-short-name`
6. **PR body MUST include** `Closes #<issue>`.
7. **Set kanban card `branch_name`** field to match the git branch.
8. **Each story gets its own kanban ID.** Do NOT reuse the EPIC-05 umbrella card (`t_dash_01`).
9. **New kanban tasks default to:** status `ready`, assignee `@platform:cursor`.

## State Machine

```
ready (open issue) → review (PR open) → done (merged + deployed on VM)
```

- Move kanban card to `review` when PR opens
- Move to `done` ONLY after: PR merged + `git pull` + `systemctl restart` + health check passes
- GitHub issue auto-closes on merge (via `Closes #N`); kanban card moves to `done` only after VM deploy

## Handoff Protocol

When Hermes finishes work, MUST comment on the GitHub issue:
1. What it did (summary)
2. VM state (service running/healthy)
3. main state (PR merged or pending)
4. Cards moved (kanban IDs + new status)
5. Unsure about (anything needing judgment)

## VM Facts

- Service: `ceo-dashboard` (systemd), port 8081, binds `127.0.0.1`
- Repo: `/home/maria_robbins/sf-project/ceo-dashboard`
- Python (systemd): venv at `/home/maria_robbins/.hermes/hermes-agent/venv/bin/python`
- Python (cron): system `python3` with `PYTHONPATH=/home/maria_robbins/.hermes/hermes-agent`
- DB: `/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db`
- Health: `curl -s http://127.0.0.1:8081/api/state | jq .`

## Templates & Guardrails

- `.github/ISSUE_TEMPLATE/story.md`
- `.github/pull_request_template.md`
- `.github/workflows/ci.yml` (Python syntax + shell lint, fails on error)
- Branch protection on `main`: PR required, **0 approvals required**, linear history (squash/rebase), no force pushes, `enforce_admins` on. CI checks are NOT enforced by GitHub, so confirm `syntax-check` and `shell-lint` are green before you merge.
- Merging: you may merge your own non-`@platform:cursor` PRs once CI is green. Maria merges `@platform:cursor` PRs and any PR changing branch protection, CI, or the workflow policy. Never use `gh pr merge --admin` or disable branch protection for a routine merge.

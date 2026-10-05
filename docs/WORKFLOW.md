# CEO Dashboard — Shared Workflow

> **Single source of truth.** Both Hermes and Cursor read this file. No more `.cursorrules`-only rules that one agent can't see.

## 1. Roles

| Role | Who | Responsibility |
|---|---|---|
| **Issue Creator** | Hermes (via auto-ticket-creator cron) or Cursor | Converts Gherkin stories → GitHub issue + kanban card |
| **Implementer** | Cursor (Agent mode) | All `@platform:cursor` stories |
| **Hermes Worker** | Hermes | Non-`@platform:cursor` stories (auto-spawned) |
| **Reviewer** | Maria (manual) or Cursor | PR review — `needs-review` label gates merge |
| **Merger** | Maria (manual) | Merges PR to `main` only after approval |
| **Deployer** | Hermes (post-merge) | `git pull` + `systemctl restart ceo-dashboard` |

## 2. State Machine

| Kanban Card Status | GitHub Issue State | GitHub PR State | Who moves it |
|---|---|---|---|
| `ready` | open | — | Issue creator (Hermes auto-ticketer or Cursor) |
| `review` | open | OPEN (draft or full) | Implementer (on PR open) |
| `done` | closed | MERGED | **Merger** merges PR, then **Deployer** deploys to VM |

**Rules:**
- A card and its issue stay **open** until the PR is merged.
- The GitHub issue **auto-closes** on PR merge (via `Closes #N`). The kanban card does **not** move to `done` until the VM is deployed and verified.
- **Never** close a GitHub issue or move a card to `done` based on VM-only state (code running on the VM but not merged to `main`).
- Hermes kanban `done` = PR merged **AND** `git pull` + `systemctl restart ceo-dashboard` + health check passed on the VM.
- `needs-review` label is set only when a PR is waiting on a human. Never set it on a story with no branch.

## 3. Hard Rules for Hermes

1. **No direct pushes to `main`.** For a production fix that can't wait, use a `hotfix/` branch and an expedited PR. Maria bypasses branch protection only for a true service outage, and a retro issue is filed afterward.
2. **Do not implement stories assigned to `@platform:cursor`.** These are Cursor's terminal lane — they wait for manual pickup in Cursor IDE.
3. **Do not close an issue or mark a card `done` before the PR merges AND the VM is updated.**
4. **After merge:** `git pull origin main` → `sudo systemctl restart ceo-dashboard` → verify with `curl -s http://127.0.0.1:8081/api/state | jq .`
5. **Naming:** Branch `feature/US-DASH-00N-short-name`, PR body includes `Closes #<issue>`, set kanban card `branch_name` to match.
6. **Each story gets its own kanban ID.** Do not reuse the EPIC-05 umbrella card (`t_dash_01`) for child stories.
7. **New kanban tasks default to:** status `ready`, assignee `@platform:cursor`.

## 4. Templates

- **Issue template:** `.github/ISSUE_TEMPLATE/story.md` — filled in by issue creator
- **PR template:** `.github/pull_request_template.md` — filled in by implementer

Both templates enforce the fields listed in section 5 below.

## 5. Required Fields per Artifact

### GitHub Issue (story)
- **Story**: What story does this implement?
- **Acceptance Criteria**: Gherkin scenarios
- **Out of Scope**: What's explicitly NOT included
- **How to Verify**: Manual or automated check
- **Docs to Update**: Which Obsidian doc or inline doc
- **Open Questions**: Anything blocking implementation

### Pull Request
- **Closes #N**: Issue reference
- **Kanban ID**: e.g., `t_dash_07`
- **What Changed**: Summary of changes
- **How it was Verified**: Test results, lint, manual checks
- **Docs Updated**: Links to any doc changes

## 6. VM Environment & Deployment

See [`docs/environment.md`](./environment.md) for:
- Service name, port, paths
- Kanban DB location
- Deploy and verify commands
- Known gotchas (python3-on-venv, etc.)

## 7. Handoff Protocol

When Hermes finishes or fixes work, add a comment on the GitHub issue covering:
1. **What it did** — summary of changes
2. **VM state** — is the service running, healthy
3. **main state** — PR merged or not
4. **Cards moved** — kanban IDs and their new status
5. **Unsure about** — anything needing human judgment

## 8. Guardrails

- **Branch protection on `main`** (GitHub repo settings): require PR before merging, require status checks, require 1 approval.
- **CI check** (`.github/workflows/ci.yml`): Python syntax check + shell lint — **fails the PR** if any check errors. Uses `+` batch mode (not `\;` which always exits 0).
- **Maria can bypass** branch protection for true emergencies (documented in §3 rule 1).

## 9. Principles (Restored from .cursorrules)

- **Docs-as-code**: If the running app and docs disagree, change the doc in the same PR. Never let them drift.
- **GitHub `main` is the only finished copy**: Code running on the VM but not merged is not "done."
- **Terminal lane**: Tasks assigned to `@platform:cursor` are Cursor's terminal lane — Hermes will NOT auto-spawn workers for them. If a previously auto-spawned task crashed, set `max_retries=0` via SQL to trip the circuit breaker before reassigning:
  ```sql
  UPDATE tasks SET max_retries=0 WHERE id='t_dash_NN';
  ```
- **Deployment method**: Use `sudo systemctl restart ceo-dashboard`. Do NOT use `cd ~/.hermes/tools && python3 ceo_dashboard_fastapi.py &` — that is the old pre-systemd method.

## 10. Where This Doc Lives

- Repo path: `docs/WORKFLOW.md` on `main`
- `.cursorrules` points here (3-line pointer)
- Hermes skill `ceo-dashboard-workflow` enforces it

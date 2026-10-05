#!/usr/bin/env python3
"""
GitHub Sync Bridge (US-DASH-004) - links GitHub issues/PRs to kanban cards.

Polling design (no webhook, no public endpoint). Run from cron every 15 minutes
via scripts/github_sync.sh. Each run:

  1. Open issue with no card      -> insert a `ready` card ("GH #N" in the body)
                                     and post ONE comment on the issue with the card id.
  2. Open PR with `Closes #N`     -> move that issue's card to `review`
                                     (and set branch_name when the column exists).
  3. Merged PR with `Closes #N`   -> leave the card in `review` and log a
                                     `merged_awaiting_deploy` event. Only the Deployer
                                     sets `done`, after the VM deploy (docs/WORKFLOW.md rule 3).

Safe to re-run: state lives in STATE_FILE and cards are matched by their "GH #N" marker.

Usage:
    python3 scripts/github_sync.py            # apply changes
    python3 scripts/github_sync.py --dry-run  # print what would happen, change nothing

Configuration (environment):
    GITHUB_REPO        owner/name (default: chicken-tights-labs/ceo-dashboard)
    KANBAN_BOARD_SLUG  board slug (default: salesforce-headless-dev)
    KANBAN_DB          full path override for the kanban DB
    GH_SYNC_STATE      state file (default: ~/.hermes/scripts/github-sync-state.json)
    GH_SYNC_SKIP_LABELS  comma list of issue labels that never get a card (default: epic)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

HOME = Path.home()
REPO = os.environ.get("GITHUB_REPO", "chicken-tights-labs/ceo-dashboard")
BOARD = os.environ.get("KANBAN_BOARD_SLUG", "salesforce-headless-dev")
KANBAN_DB = Path(
    os.environ.get("KANBAN_DB", str(HOME / ".hermes/kanban/boards" / BOARD / "kanban.db"))
)
STATE_FILE = Path(
    os.environ.get("GH_SYNC_STATE", str(HOME / ".hermes/scripts/github-sync-state.json"))
)
SKIP_LABELS = {
    s.strip().lower()
    for s in os.environ.get("GH_SYNC_SKIP_LABELS", "epic").split(",")
    if s.strip()
}
WORKER_MODEL = "claude-3.5-sonnet"

# Card statuses a PR-open event may move to `review`. Never pull a card back
# from done/blocked/archived, and never re-move one already in review.
REVIEWABLE_FROM = {"ready", "todo", "running"}

CLOSES_RE = re.compile(r"\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)", re.IGNORECASE)


# -- GitHub access (replaceable in tests) ------------------------------------
def run_gh(args: list[str]) -> str:
    """Run a gh command and return stdout. Raises on failure."""
    result = subprocess.run(
        ["gh", *args], capture_output=True, text=True, check=True, timeout=60
    )
    return result.stdout


def fetch_issues(gh=run_gh) -> list[dict]:
    out = gh([
        "issue", "list", "--repo", REPO, "--state", "open", "--limit", "200",
        "--json", "number,title,body,labels,url",
    ])
    return json.loads(out or "[]")


def fetch_prs(gh=run_gh) -> list[dict]:
    out = gh([
        "pr", "list", "--repo", REPO, "--state", "all", "--limit", "100",
        "--json", "number,title,body,state,headRefName,mergedAt,url",
    ])
    return json.loads(out or "[]")


def comment_on_issue(number: int, text: str, gh=run_gh) -> None:
    gh(["issue", "comment", str(number), "--repo", REPO, "--body", text])


# -- State -------------------------------------------------------------------
def load_state(path: Path = STATE_FILE) -> dict:
    default = {"issues": {}, "commented": [], "pr_seen": {}}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for key, value in default.items():
                data.setdefault(key, value)
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_state(state: dict, path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


# -- Kanban DB ---------------------------------------------------------------
def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    return conn


def task_columns(conn: sqlite3.Connection) -> set[str]:
    return {row["name"] for row in conn.execute("PRAGMA table_info(tasks)")}


def marker(number: int) -> str:
    return f"GH #{number}"


def find_card_for_issue(conn: sqlite3.Connection, number: int) -> str | None:
    """Find an existing card by its 'GH #N' marker (whole-number match)."""
    pattern = re.compile(rf"GH #{number}(?!\d)")
    rows = conn.execute(
        "SELECT id, body FROM tasks WHERE status != 'archived' AND body LIKE ?",
        (f"%GH #{number}%",),
    ).fetchall()
    for row in rows:
        if row["body"] and pattern.search(row["body"]):
            return row["id"]
    return None


def add_event(conn: sqlite3.Connection, task_id: str, kind: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (task_id, None, kind, json.dumps(payload), int(time.time())),
    )


def create_card(conn: sqlite3.Connection, issue: dict) -> str:
    """Insert a ready card for a GitHub issue, assigned to the Cursor lane by default."""
    task_id = "t-" + uuid.uuid4().hex[:12]
    labels = ", ".join(lbl["name"] for lbl in issue.get("labels", []))
    body = (
        f"**{marker(issue['number'])}** - {issue.get('url', '')}\n"
        f"Labels: `{labels}`\n\n"
        f"{(issue.get('body') or '').strip()}"
    )
    conn.execute(
        "INSERT INTO tasks (id, title, body, assignee, status, workspace_kind, "
        "workspace_path, tenant, created_at, created_by, consecutive_failures) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id, issue["title"], body,
            f"@platform:cursor @used-model:{WORKER_MODEL}",
            "ready", "scratch", None, None, int(time.time()), "github-sync", 0,
        ),
    )
    add_event(conn, task_id, "created", {"by": "github-sync", "issue": issue["number"]})
    return task_id


def move_to_review(conn: sqlite3.Connection, task_id: str, pr: dict, columns: set[str]) -> bool:
    row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None or row["status"] not in REVIEWABLE_FROM:
        return False
    if "branch_name" in columns:
        conn.execute(
            "UPDATE tasks SET status = 'review', branch_name = ? WHERE id = ?",
            (pr.get("headRefName"), task_id),
        )
    else:
        conn.execute("UPDATE tasks SET status = 'review' WHERE id = ?", (task_id,))
    add_event(conn, task_id, "github_sync", {
        "change": "status", "from": row["status"], "to": "review",
        "pr": pr["number"], "branch": pr.get("headRefName"),
    })
    return True


def linked_issues(pr: dict) -> list[int]:
    return sorted({int(n) for n in CLOSES_RE.findall(pr.get("body") or "")})


# -- Sync --------------------------------------------------------------------
def sync(conn, issues, prs, state, commenter, dry_run=False, log=print) -> dict:
    """Reconcile issues/PRs into the DB. Returns counters. Mutates `state`."""
    counts = {"created": 0, "reviewed": 0, "merged_noted": 0, "commented": 0}
    columns = task_columns(conn)

    # 1. open issues -> cards
    for issue in issues:
        number = issue["number"]
        label_names = {lbl["name"].lower() for lbl in issue.get("labels", [])}
        if label_names & SKIP_LABELS:
            log(f"  skip #{number} (label in {sorted(SKIP_LABELS)})")
            continue
        key = str(number)
        task_id = state["issues"].get(key) or find_card_for_issue(conn, number)
        if task_id is None:
            if dry_run:
                log(f"  [dry-run] would create card for #{number}: {issue['title']}")
                continue
            task_id = create_card(conn, issue)
            counts["created"] += 1
            log(f"  created {task_id} for #{number}")
        state["issues"][key] = task_id

        if number not in state["commented"]:
            if dry_run:
                log(f"  [dry-run] would comment kanban id on #{number}")
            else:
                try:
                    commenter(number, f"Kanban card: `{task_id}` (linked by github-sync)")
                    state["commented"].append(number)
                    counts["commented"] += 1
                except (subprocess.SubprocessError, OSError) as exc:
                    log(f"  WARN: comment on #{number} failed: {exc}")

    # 2/3. PRs -> status changes
    for pr in prs:
        pr_state = "merged" if pr.get("mergedAt") else pr["state"].lower()
        for number in linked_issues(pr):
            task_id = state["issues"].get(str(number)) or find_card_for_issue(conn, number)
            if task_id is None:
                continue
            seen_key = f"{pr['number']}:{number}"
            if pr_state == "open":
                if dry_run:
                    log(f"  [dry-run] would move {task_id} to review (PR #{pr['number']})")
                elif move_to_review(conn, task_id, pr, columns):
                    counts["reviewed"] += 1
                    log(f"  {task_id} -> review (PR #{pr['number']})")
            elif pr_state == "merged" and state["pr_seen"].get(seen_key) != "merged":
                if dry_run:
                    log(f"  [dry-run] would note merge of PR #{pr['number']} on {task_id}")
                else:
                    add_event(conn, task_id, "merged_awaiting_deploy", {
                        "pr": pr["number"], "issue": number,
                        "note": "PR merged; Deployer sets done after VM deploy + health check",
                    })
                    state["pr_seen"][seen_key] = "merged"
                    counts["merged_noted"] += 1
                    log(f"  {task_id}: PR #{pr['number']} merged, awaiting deploy")
    if not dry_run:
        conn.commit()
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--dry-run", action="store_true", help="show actions, change nothing")
    args = parser.parse_args(argv)

    if not KANBAN_DB.exists():
        print(f"ERROR: Kanban DB not found at {KANBAN_DB}")
        return 1
    try:
        issues, prs = fetch_issues(), fetch_prs()
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: could not read GitHub via gh: {exc}")
        return 1

    state = load_state()
    conn = connect(KANBAN_DB)
    try:
        counts = sync(conn, issues, prs, state, comment_on_issue, dry_run=args.dry_run)
    finally:
        conn.close()
    if not args.dry_run:
        save_state(state)
    print(f"Done: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Tests for scripts/github_sync.py using a temp SQLite DB and canned GitHub data.

Run from the repo root:  python -m unittest discover -s tests -v
"""
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import github_sync as gs  # noqa: E402


def make_db(with_branch_column=True) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    branch = ", branch_name TEXT" if with_branch_column else ""
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, assignee TEXT, "
        "status TEXT, workspace_kind TEXT, workspace_path TEXT, tenant TEXT, "
        f"created_at INTEGER, created_by TEXT, consecutive_failures INTEGER{branch})"
    )
    conn.execute(
        "CREATE TABLE task_events (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, "
        "run_id TEXT, kind TEXT, payload TEXT, created_at INTEGER)"
    )
    return conn


def fresh_state():
    return {"issues": {}, "commented": [], "pr_seen": {}}


ISSUE_5 = {"number": 5, "title": "US-DASH-004: GitHub Sync Bridge", "body": "body",
           "labels": [{"name": "feature"}], "url": "https://example/issues/5"}
EPIC_12 = {"number": 12, "title": "EPIC-05", "body": "", "labels": [{"name": "epic"}], "url": ""}


def pr(number, body, state="OPEN", merged=None, branch="feature/x"):
    return {"number": number, "title": "t", "body": body, "state": state,
            "headRefName": branch, "mergedAt": merged, "url": ""}


class GithubSyncTests(unittest.TestCase):
    def setUp(self):
        self.conn = make_db()
        self.comments = []
        self.commenter = lambda n, text: self.comments.append((n, text))
        self.quiet = lambda *_: None

    def run_sync(self, issues, prs, state=None, dry_run=False):
        state = state if state is not None else fresh_state()
        counts = gs.sync(self.conn, issues, prs, state, self.commenter,
                         dry_run=dry_run, log=self.quiet)
        return counts, state

    def test_open_issue_creates_ready_card_and_one_comment(self):
        counts, state = self.run_sync([ISSUE_5], [])
        self.assertEqual(counts["created"], 1)
        row = self.conn.execute("SELECT * FROM tasks").fetchone()
        self.assertEqual(row["status"], "ready")
        self.assertIn("@platform:cursor", row["assignee"])
        self.assertIn("GH #5", row["body"])
        self.assertEqual(state["issues"]["5"], row["id"])
        self.assertEqual(len(self.comments), 1)
        self.assertIn(row["id"], self.comments[0][1])

    def test_rerun_is_idempotent(self):
        _, state = self.run_sync([ISSUE_5], [])
        counts, _ = self.run_sync([ISSUE_5], [], state=state)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)
        self.assertEqual(len(self.comments), 1)

    def test_lost_state_does_not_duplicate_card(self):
        self.run_sync([ISSUE_5], [])
        counts, _ = self.run_sync([ISSUE_5], [], state=fresh_state())
        self.assertEqual(counts["created"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 1)

    def test_marker_does_not_match_longer_issue_number(self):
        self.conn.execute(
            "INSERT INTO tasks (id, title, body, status) VALUES ('t-x', 'x', 'GH #50', 'ready')")
        counts, _ = self.run_sync([ISSUE_5], [])
        self.assertEqual(counts["created"], 1)

    def test_epic_label_is_skipped(self):
        counts, _ = self.run_sync([EPIC_12], [])
        self.assertEqual(counts["created"], 0)

    def test_open_pr_moves_card_to_review_and_sets_branch(self):
        _, state = self.run_sync([ISSUE_5], [])
        counts, _ = self.run_sync([ISSUE_5], [pr(30, "Closes #5", branch="feature/US-DASH-004")],
                                  state=state)
        self.assertEqual(counts["reviewed"], 1)
        row = self.conn.execute("SELECT * FROM tasks").fetchone()
        self.assertEqual(row["status"], "review")
        self.assertEqual(row["branch_name"], "feature/US-DASH-004")

    def test_works_without_branch_name_column(self):
        self.conn = make_db(with_branch_column=False)
        _, state = self.run_sync([ISSUE_5], [])
        counts, _ = self.run_sync([ISSUE_5], [pr(30, "Closes #5")], state=state)
        self.assertEqual(counts["reviewed"], 1)

    def test_merged_pr_never_sets_done(self):
        _, state = self.run_sync([ISSUE_5], [pr(30, "Closes #5")])
        merged = pr(30, "Closes #5", state="MERGED", merged="2026-10-05T12:00:00Z")
        counts, state = self.run_sync([], [merged], state=state)
        self.assertEqual(counts["merged_noted"], 1)
        self.assertNotEqual(self.conn.execute("SELECT status FROM tasks").fetchone()[0], "done")
        kinds = [r[0] for r in self.conn.execute("SELECT kind FROM task_events")]
        self.assertIn("merged_awaiting_deploy", kinds)
        counts, _ = self.run_sync([], [merged], state=state)
        self.assertEqual(counts["merged_noted"], 0)

    def test_done_or_blocked_card_is_not_moved(self):
        _, state = self.run_sync([ISSUE_5], [])
        self.conn.execute("UPDATE tasks SET status = 'blocked'")
        counts, _ = self.run_sync([ISSUE_5], [pr(30, "Closes #5")], state=state)
        self.assertEqual(counts["reviewed"], 0)
        self.assertEqual(self.conn.execute("SELECT status FROM tasks").fetchone()[0], "blocked")

    def test_dry_run_changes_nothing(self):
        counts, state = self.run_sync([ISSUE_5], [], dry_run=True)
        self.assertEqual(counts["created"], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0], 0)
        self.assertEqual(self.comments, [])
        self.assertEqual(state["issues"], {})

    def test_comment_failure_is_retried_next_run(self):
        def boom(n, text):
            raise OSError("gh down")
        state = fresh_state()
        gs.sync(self.conn, [ISSUE_5], [], state, boom, log=self.quiet)
        self.assertEqual(state["commented"], [])
        counts, _ = self.run_sync([ISSUE_5], [], state=state)
        self.assertEqual(counts["commented"], 1)

    def test_closes_parsing(self):
        self.assertEqual(gs.linked_issues({"body": "Closes #5, fixes #19 and resolved: #7"}),
                         [5, 7, 19])
        self.assertEqual(gs.linked_issues({"body": None}), [])


if __name__ == "__main__":
    unittest.main()

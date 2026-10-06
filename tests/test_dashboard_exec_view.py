"""Tests for the CEO Dashboard executive view (DASH-only, grouped by epic).

Covers US-DASH-014: the exec view must show only DASH tasks (not Salesforce
US-T*/US-F*/US-D* tasks), grouped by epic, with AI vs human color coding.

Run from the repo root:
    python -m unittest tests.test_dashboard_exec_view -v
"""
import json
import sqlite3
import tempfile
import shutil
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "src" / "dashboard_server.py"


def load_server(db_path: str):
    """Import src/dashboard_server.py with KANBAN_DB pointed at a temp DB."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "dashboard_server_exec_test", SERVER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.KANBAN_DB = db_path
    return module


def make_db(path: str, tasks: list[dict]) -> None:
    """Create a kanban DB with the given task rows and task_links."""
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY, title TEXT, body TEXT, assignee TEXT,
            status TEXT, priority INTEGER, created_at INTEGER,
            workspace_path TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_links (
            parent_id TEXT NOT NULL, child_id TEXT NOT NULL,
            PRIMARY KEY (parent_id, child_id)
        )
        """
    )
    for t in tasks:
        conn.execute(
            """
            INSERT INTO tasks
                (id, title, body, assignee, status, priority, created_at, workspace_path)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t["id"], t.get("title", ""), t.get("body", ""),
                t.get("assignee", "-"), t["status"],
                t.get("priority", 0), t.get("created_at", 1700000000),
                t.get("workspace_path", None),
            ),
        )
    conn.commit()
    conn.close()


class DashboardExecViewTests(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="dash-exec-test-"))
        self.db = str(self.tmpdir / "kanban.db")

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    # ------------------------------------------------------------------
    # DASH identification
    # ------------------------------------------------------------------

    def test_dash_tasks_are_included_salesforce_excluded(self):
        """Only US-DASH/EPIC-05/CEO-Dashboard tasks appear; US-T, US-F, US-D do not."""
        tasks = [
            {"id": "t-dash-001", "title": "US-DASH-001: Static Kanban Mirror",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "done", "priority": 1, "created_at": 1700000000},
            {"id": "t-dash-005", "title": "US-DASH-005: Daily Digest",
             "assignee": "-", "status": "ready", "priority": 1, "created_at": 1700000001},
            {"id": "t-05-epic", "title": "EPIC-05: CEO Dashboard Development",
             "assignee": "default", "status": "done", "priority": 0, "created_at": 1700000002},
            # Salesforce tasks — must NOT appear
            {"id": "t-t001", "title": "US-T001: Trainer View Schedule",
             "assignee": "-", "status": "todo", "priority": 2, "created_at": 1700000003},
            {"id": "t-f001", "title": "US-F001: Register Walk-In Lead",
             "assignee": "-", "status": "todo", "priority": 2, "created_at": 1700000004},
            {"id": "t-d001", "title": "US-D001: End User Manual",
             "assignee": "-", "status": "todo", "priority": 2, "created_at": 1700000005},
            {"id": "t-epic-03", "title": "EPIC-03: Trainer Operations",
             "assignee": "-", "status": "ready", "priority": 2, "created_at": 1700000006},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()
        all_titles = [t["title"] for e in state["epics"].values() for t in e["tasks"]]

        self.assertIn("US-DASH-001: Static Kanban Mirror", all_titles)
        self.assertIn("US-DASH-005: Daily Digest", all_titles)
        # EPIC-05 itself is a group header, not a task row
        epic_key = "EPIC-05: CEO Dashboard Development"
        self.assertIn(epic_key, state["epics"])
        # Salesforce tasks must NOT appear
        self.assertNotIn("US-T001: Trainer View Schedule", all_titles)
        self.assertNotIn("US-F001: Register Walk-In Lead", all_titles)
        self.assertNotIn("US-D001: End User Manual", all_titles)
        self.assertNotIn("EPIC-03: Trainer Operations", all_titles)
        self.assertEqual(state["stats"]["total"], 2)

    # ------------------------------------------------------------------
    # Epic grouping
    # ------------------------------------------------------------------

    def test_tasks_linked_to_epic_are_grouped_under_epic(self):
        """Tasks via task_links.parent_id = EPIC-05 appear under that epic's group."""
        tasks = [
            {"id": "t_dash_01", "title": "EPIC-05: CEO Dashboard Development",
             "assignee": "default", "status": "done", "priority": 0, "created_at": 1700000000},
            {"id": "t_dash_02", "title": "US-DASH-001: Static Kanban Mirror Export",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "done", "priority": 1, "created_at": 1700000001},
            {"id": "t_dash_03", "title": "US-DASH-002: Auto-Ticket Creator",
             "assignee": "default", "status": "done", "priority": 1, "created_at": 1700000002},
        ]
        make_db(self.db, tasks)
        # Link children to EPIC-05
        conn = sqlite3.connect(self.db)
        conn.execute("INSERT INTO task_links (parent_id, child_id) VALUES ('t_dash_01', 't_dash_02')")
        conn.execute("INSERT INTO task_links (parent_id, child_id) VALUES ('t_dash_01', 't_dash_03')")
        conn.commit()
        conn.close()

        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()

        epic_key = "EPIC-05: CEO Dashboard Development"
        self.assertIn(epic_key, state["epics"])
        # Two children grouped under the epic
        task_titles = [t["title"] for t in state["epics"][epic_key]["tasks"]]
        self.assertIn("US-DASH-001: Static Kanban Mirror Export", task_titles)
        self.assertIn("US-DASH-002: Auto-Ticket Creator", task_titles)
        self.assertEqual(len(task_titles), 2)

    def test_unlinked_dash_tasks_grouped_as_other(self):
        """US-DASH tasks not linked to any epic go into 'Other DASH Tasks'."""
        tasks = [
            {"id": "t-dash-013", "title": "US-DASH-013: /ceo-dashboard public route",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "ready", "priority": 0, "created_at": 1700000000,
             "workspace_path": None},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()

        self.assertIn("Other DASH Tasks", state["epics"])
        titles = [t["title"] for t in state["epics"]["Other DASH Tasks"]["tasks"]]
        self.assertIn("US-DASH-013: /ceo-dashboard public route", titles)

    # ------------------------------------------------------------------
    # AI vs human detection
    # ------------------------------------------------------------------

    def test_ai_assigned_tasks_are_flagged(self):
        """Tasks with @platform:cursor are flagged as AI."""
        tasks = [
            {"id": "t1", "title": "US-DASH-001: Test AI",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "ready", "priority": 1, "created_at": 1700000000},
            {"id": "t2", "title": "US-DASH-002: Test Human",
             "assignee": "default", "status": "ready", "priority": 1, "created_at": 1700000001},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()

        all_tasks = [t for e in state["epics"].values() for t in e["tasks"]]
        ai_tasks = [t for t in all_tasks if t["is_ai"]]
        human_tasks = [t for t in all_tasks if not t["is_ai"]]

        self.assertEqual(len(ai_tasks), 1)
        self.assertEqual(ai_tasks[0]["title"], "US-DASH-001: Test AI")
        self.assertEqual(ai_tasks[0]["platform"], "CURSOR")
        self.assertEqual(ai_tasks[0]["model"], "claude 3.5 sonnet")

        self.assertEqual(len(human_tasks), 1)
        self.assertEqual(human_tasks[0]["title"], "US-DASH-002: Test Human")

    def test_bracketed_platform_is_detected_as_ai(self):
        """'default [@platform:cursor]' should be detected as AI-assigned."""
        tasks = [
            {"id": "t1", "title": "US-DASH-001: Bracket AI",
             "assignee": "default [@platform:cursor]",
             "status": "ready", "priority": 1, "created_at": 1700000000},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()
        all_tasks = [t for e in state["epics"].values() for t in e["tasks"]]
        self.assertTrue(all_tasks[0]["is_ai"])

    # ------------------------------------------------------------------
    # Auto-ticket identification
    # ------------------------------------------------------------------

    def test_auto_tickets_from_ceo_dashboard_repo_are_included(self):
        """[Auto] tickets with workspace_path=c.../ceo-dashboard are DASH."""
        tasks = [
            {"id": "t-auto-001", "title": "[Auto] View live board status",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "ready", "priority": 5, "created_at": 1700000000,
             "workspace_path": "/home/maria_robbins/sf-project/ceo-dashboard"},
            {"id": "t-auto-002", "title": "[Auto] Some Salesforce thing",
             "assignee": "@platform:cursor",
             "status": "ready", "priority": 5, "created_at": 1700000001,
             "workspace_path": "/home/maria_robbins/sf-project/salesforce-headless-dev"},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()
        all_titles = [t["title"] for e in state["epics"].values() for t in e["tasks"]]

        self.assertIn("[Auto] View live board status", all_titles)
        self.assertNotIn("[Auto] Some Salesforce thing", all_titles)

    # ------------------------------------------------------------------
    # Stats accuracy
    # ------------------------------------------------------------------

    def test_stats_are_correct(self):
        """Stats counts reflect the DASH-only subset."""
        tasks = [
            {"id": "t1", "title": "US-DASH-001: Task 1",
             "assignee": "@platform:cursor", "status": "done", "priority": 1, "created_at": 1700000000},
            {"id": "t2", "title": "US-DASH-002: Task 2",
             "assignee": "default", "status": "ready", "priority": 1, "created_at": 1700000001},
            {"id": "t3", "title": "US-DASH-003: Task 3",
             "assignee": "@platform:cursor @used-model:claude-3.5-sonnet",
             "status": "todo", "priority": 1, "created_at": 1700000002},
            # Salesforce task — excluded
            {"id": "t4", "title": "US-T001: Trainer Task",
             "assignee": "default", "status": "done", "priority": 1, "created_at": 1700000003},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()

        s = state["stats"]
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["ai_assigned"], 2)
        self.assertEqual(s["human_review"], 1)
        self.assertEqual(s["complete"], 1)
        self.assertEqual(s["queued"], 1)
        self.assertEqual(s["backlog"], 1)

    # ------------------------------------------------------------------
    # Full board still has everything
    # ------------------------------------------------------------------

    def test_full_board_includes_all_tasks(self):
        """get_board_state is unchanged — still returns all non-archived tasks."""
        tasks = [
            {"id": "t1", "title": "US-DASH-001: DASH Task",
             "assignee": "@platform:cursor", "status": "ready", "priority": 1, "created_at": 1700000000},
            {"id": "t2", "title": "US-T001: Trainer Task",
             "assignee": "default", "status": "todo", "priority": 1, "created_at": 1700000001},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        board = server.get_board_state()
        total = sum(len(v) for v in board.values())
        self.assertEqual(total, 2)
        # Both statuses present
        self.assertGreaterEqual(len(board.get("ready", [])), 1)
        self.assertGreaterEqual(len(board.get("todo", [])), 1)

    # ------------------------------------------------------------------
    # Archived excluded
    # ------------------------------------------------------------------

    def test_archived_tasks_excluded_from_ceo_view(self):
        tasks = [
            {"id": "t1", "title": "US-DASH-001: Active",
             "assignee": "@platform:cursor", "status": "ready", "priority": 1, "created_at": 1700000000},
            {"id": "t2", "title": "US-DASH-002: Archived",
             "assignee": "@platform:cursor", "status": "archived", "priority": 1, "created_at": 1700000001},
        ]
        make_db(self.db, tasks)
        server = load_server(self.db)
        state = server.get_ceo_dashboard_state()
        all_titles = [t["title"] for e in state["epics"].values() for t in e["tasks"]]
        self.assertIn("US-DASH-001: Active", all_titles)
        self.assertNotIn("US-DASH-002: Archived", all_titles)


if __name__ == "__main__":
    unittest.main()

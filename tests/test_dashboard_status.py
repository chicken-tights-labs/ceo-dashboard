"""Regression tests for the dashboard board renderer.

Covers the KeyError bug where a card in a valid-but-unhandled kanban status
(`review`, `triage`, `scheduled`) took the whole dashboard down.

Run from the repo root:  python -m unittest discover -s tests -v
"""
import importlib.util
import sqlite3
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = REPO_ROOT / "src" / "dashboard_server.py"

# All statuses Hermes' kanban accepts (hermes_cli/kanban_db.py VALID_STATUSES).
# `archived` is excluded from the board by the SQL filter.
HERMES_VALID_STATUSES = [
    "triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done",
]


def load_server(db_path: str):
    """Import src/dashboard_server.py with KANBAN_DB pointed at a temp DB."""
    spec = importlib.util.spec_from_file_location("dashboard_server_under_test", SERVER_PATH)
    module = importlib.util.module_from_spec(spec)
    # Set before exec: the module reads KANBAN_DB at import for the default arg,
    # and get_board_state() reads the module global at call time.
    spec.loader.exec_module(module)
    module.KANBAN_DB = db_path
    return module


def make_db(path: str, statuses: list[str]) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, title TEXT, body TEXT, assignee TEXT, "
        "status TEXT, priority INTEGER, created_at INTEGER)"
    )
    for i, status in enumerate(statuses):
        conn.execute(
            "INSERT INTO tasks (id, title, body, assignee, status, priority, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (f"t-{i:04d}{status[:4]}", f"Card {status}", "body", "@platform:cursor", status, 0, 1700000000 + i),
        )
    conn.commit()
    conn.close()


class DashboardStatusTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmpdir = Path(tempfile.mkdtemp(prefix="dash-status-test-"))
        self.db = str(self.tmpdir / "kanban.db")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_every_valid_hermes_status_renders(self):
        """No valid kanban status may raise — this is the bug from #25."""
        make_db(self.db, HERMES_VALID_STATUSES)
        server = load_server(self.db)
        board = server.get_board_state()
        for status in HERMES_VALID_STATUSES:
            self.assertIn(status, board, f"status {status!r} missing from board")
            self.assertEqual(len(board[status]), 1, f"status {status!r} lost its card")

    def test_review_status_does_not_raise_keyerror(self):
        """The exact regression: a card in `review` used to crash the dashboard."""
        make_db(self.db, ["review"])
        server = load_server(self.db)
        try:
            board = server.get_board_state()
        except KeyError as exc:  # pragma: no cover - this is the failure we guard
            self.fail(f"get_board_state raised KeyError for 'review': {exc}")
        self.assertIn("review", board)

    def test_unknown_status_is_rendered_not_dropped(self):
        """A status the dashboard has never heard of degrades gracefully."""
        make_db(self.db, ["ready", "some_future_status"])
        server = load_server(self.db)
        board = server.get_board_state()
        self.assertIn("some_future_status", board)
        self.assertEqual(len(board["some_future_status"]), 1)

    def test_known_statuses_come_before_unknown(self):
        make_db(self.db, ["some_future_status", "ready", "done"])
        server = load_server(self.db)
        board = server.get_board_state()
        keys = list(board.keys())
        self.assertLess(keys.index("ready"), keys.index("some_future_status"))
        self.assertLess(keys.index("done"), keys.index("some_future_status"))

    def test_archived_is_excluded(self):
        make_db(self.db, ["ready", "archived"])
        server = load_server(self.db)
        board = server.get_board_state()
        self.assertNotIn("archived", board)
        self.assertEqual(sum(len(v) for v in board.values()), 1)

    def test_summary_total_counts_every_column(self):
        """stats.total must include cards in unexpected statuses."""
        make_db(self.db, ["ready", "review", "done", "some_future_status"])
        server = load_server(self.db)
        board = server.get_board_state()
        stats = server.get_summary_stats(board)
        self.assertEqual(stats["total"], 4)
        self.assertEqual(stats["review"], 1)
        self.assertEqual(stats["queued"], 1)
        self.assertEqual(stats["complete"], 1)

    def test_summary_stats_tolerate_missing_columns(self):
        make_db(self.db, ["some_future_status"])
        server = load_server(self.db)
        board = server.get_board_state()
        stats = server.get_summary_stats(board)
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["blocked"], 0)
        self.assertEqual(stats["review"], 0)

    def test_status_metadata_covers_display_statuses(self):
        """Every status we intend to show needs a colour and a label."""
        server = load_server(self.db)
        for status in server.STATUS_ORDER:
            self.assertIn(status, server.STATUS_COLORS, f"{status} has no colour")
            self.assertIn(status, server.STATUS_LABELS, f"{status} has no label")
        self.assertNotIn("archived", server.STATUS_ORDER)

    def test_html_render_with_review_card(self):
        """End-to-end: the Jinja template renders with a review card present."""
        make_db(self.db, ["ready", "review", "done"])
        server = load_server(self.db)
        board = server.get_board_state()
        template = server._env.get_template("dashboard.html")
        html = template.render(
            request=None,
            board=board,
            stats=server.get_summary_stats(board),
            status_labels=server.STATUS_LABELS,
            status_colors=server.STATUS_COLORS,
            status_order=list(board.keys()),
            unknown_status_color=server.UNKNOWN_STATUS_COLOR,
            last_updated="test",
        )
        self.assertIn("In Review", html)
        self.assertIn("Card review", html)

    def test_html_render_with_unknown_status(self):
        make_db(self.db, ["some_future_status"])
        server = load_server(self.db)
        board = server.get_board_state()
        template = server._env.get_template("dashboard.html")
        html = template.render(
            request=None,
            board=board,
            stats=server.get_summary_stats(board),
            status_labels=server.STATUS_LABELS,
            status_colors=server.STATUS_COLORS,
            status_order=list(board.keys()),
            unknown_status_color=server.UNKNOWN_STATUS_COLOR,
            last_updated="test",
        )
        # Falls back to the raw status string as the column heading.
        self.assertIn("some_future_status", html)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
Auto-Ticket Creator — Scans Obsidian/Gherkin requirements for @cursor scenarios.
Creates ready-state kanban tickets assigned to the Cursor agent.

Run via cron (hourly) — no Hermes daemon or human approval needed.

Usage:
    python3 ~/.hermes/scripts/auto_ticket_creator.py

Configuration:
    OBSIDIAN_REQS_FILE — path to the Gherkin requirements file
    KANBAN_BOARD_SLUG  — board slug (default: salesforce-headless-dev)
    STATE_FILE         — persists processed scenario hashes
"""
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
HOME = Path.home()
OBSIDIAN_REQS_FILE = os.environ.get(
    "OBSIDIAN_REQS_FILE",
    str(HOME / "sf-project/ceo-dashboard/tasks/requirements.md"),
)
KANBAN_BOARD_SLUG = os.environ.get("KANBAN_BOARD_SLUG", "salesforce-headless-dev")
KANBAN_DB = HOME / ".hermes/kanban/boards/" / KANBAN_BOARD_SLUG / "kanban.db"
STATE_FILE = Path(
    os.environ.get(
        "STATE_FILE",
        str(HOME / ".hermes/scripts/auto-ticket-state.json"),
    )
)
WORKER_MODEL = "claude-3.5-sonnet"

# ── Gherkin parser ────────────────────────────────────────────────────────────
# Matches: Scenario: NAME → gherkin code block containing @cursor tag
# Looks for @cursor anywhere in the scenario block (before Scenario: or in gherkin body)
SCENARIO_RE = re.compile(
    r"Scenario:\s*(.+?)\s*\n"    # group 1: scenario name
    r"(.*?)"                        # group 2: everything until next Scenario or Feature
    r"(?=Scenario:|##\s+Feature:|$)",  # lookahead for next boundary
    re.DOTALL,
)

GHERKIN_BLOCK_RE = re.compile(r"```gherkin\n(.*?)\n```", re.DOTALL)

def parse_gherkin_file(path: str) -> list[dict]:
    """Extract Gherkin scenarios with @cursor tags from the requirements file."""
    if not os.path.exists(path):
        print(f"  ⚠️  Requirements file not found: {path}")
        return []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    scenarios: list[dict] = []

    for m in SCENARIO_RE.finditer(content):
        name = m.group(1).strip()
        scenario_block = m.group(2)

        # Check for @cursor in the scenario block
        tags = re.findall(r"@[\w\-]+", scenario_block)
        if "@cursor" not in tags:
            continue

        # Extract gherkin content from code block
        gherkin_match = GHERKIN_BLOCK_RE.search(scenario_block)
        if gherkin_match:
            gherkin_body = gherkin_match.group(1).strip()
        else:
            gherkin_body = scenario_block.strip()

        scenarios.append({
            "name": name,
            "gherkin": f"Scenario: {name}\n{gherkin_body}",
            "tags": tags,
        })

    return scenarios


def scenario_hash(scenario: dict) -> str:
    """Hash a scenario for deduplication — based on name + gherkin body."""
    h = hashlib.sha256()
    h.update(scenario["name"].encode("utf-8"))
    h.update(scenario["gherkin"].encode("utf-8"))
    return h.hexdigest()[:16]


# ── State persistence ─────────────────────────────────────────────────────────
def load_state() -> dict:
    """Load processed scenario hashes from state file."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {"processed": {}}


def save_state(state: dict) -> None:
    """Save processed scenario hashes to state file."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ── Kanban ticket creation ────────────────────────────────────────────────────
def create_kanban_ticket(scenario: dict) -> str:
    """Insert a ticket into the kanban DB with status='ready'."""
    conn = sqlite3.connect(str(KANBAN_DB))
    conn.execute("PRAGMA busy_timeout=5000")
    now = int(time.time())

    task_id = "t-" + uuid.uuid4().hex[:12]
    title = f"US: {scenario['name']}"
    body = (
        f"**Auto-created from Gherkin requirement**\n\n"
        f"Source: `{OBSIDIAN_REQS_FILE}`\n"
        f"Labels: `platform:cursor, needs-review`\n\n"
        f"```gherkin\n{scenario['gherkin']}\n```"
    )

    conn.execute(
        "INSERT INTO tasks (id, title, body, assignee, status, workspace_kind, "
        "workspace_path, tenant, created_at, created_by, consecutive_failures) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id, title, body,
            f"@platform:cursor @used-model:{WORKER_MODEL}",
            "ready", "scratch", None, None, now, "bot", 0,
        ),
    )
    conn.execute(
        "INSERT INTO task_events (task_id, run_id, kind, payload, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (task_id, None, "created", json.dumps({"by": "bot"}), now),
    )
    conn.commit()
    conn.close()
    return task_id


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    if not KANBAN_DB.exists():
        print(f"ERROR: Kanban DB not found at {KANBAN_DB}")
        sys.exit(1)

    # 1. Parse Gherkin scenarios
    scenarios = parse_gherkin_file(OBSIDIAN_REQS_FILE)
    if not scenarios:
        print("No @cursor scenarios found.")
        return

    print(f"Found {len(scenarios)} @cursor scenario(s) in requirements file.")

    # 2. Load state (track processed scenarios)
    state = load_state()
    new_count = 0

    for scenario in scenarios:
        h = scenario_hash(scenario)
        if h in state["processed"]:
            print(f"  ⏭️  Skip (already processed): {scenario['name']}")
            continue

        # 3. Create kanban ticket
        task_id = create_kanban_ticket(scenario)
        state["processed"][h] = task_id
        new_count += 1
        print(f"  ✅ Created: {task_id} — {scenario['name']}")

    # 4. Save state
    if new_count > 0:
        save_state(state)

    print(f"\nDone: {new_count} new ticket(s) created, {len(scenarios) - new_count} skipped.")


if __name__ == "__main__":
    main()

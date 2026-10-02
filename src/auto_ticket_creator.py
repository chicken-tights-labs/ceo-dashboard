#!/usr/bin/env python3
"""
Auto-Ticket Creator - Scans Obsidian for Gherkin stories tagged @cursor
and creates kanban tickets for each unique scenario

Watches: Obsidian Vault/CRM-Documentation/ and Obsidian Vault/CEO-Dashboard/tasks/
Trigger: Any .md file containing @cursor and a Scenario:
Output: New kanban ticket on salesforce-headless-dev board
"""
import sqlite3
import os
import re
import hashlib
from pathlib import Path
from datetime import datetime

KANBAN_DB = "/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db"
OBSIDIAN_VAULT = Path("/home/maria_robbins/Documents/Obsidian Vault")
SCAN_DIRS = [
    OBSIDIAN_VAULT / "CRM-Documentation",
    OBSIDIAN_VAULT / "CEO-Dashboard" / "tasks",
    OBSIDIAN_VAULT / "Projects",
    Path("/home/maria_robbins/sf-project/ceo-dashboard/tasks"),  # Repo task directory
]
MARKER_FILE = Path("/home/maria_robbins/.hermes/cache/scratch/auto-ticket-seen.txt")

GITOKEN_PATTERN = re.compile(r"@cursor", re.IGNORECASE)
SCENARIO_PATTERN = re.compile(r"### Scenario: (.+)", re.IGNORECASE)
GHERKIN_BLOCK = re.compile(
    r"### Scenario:\s*(.+?)(?:\n```gherkin\s*(.*?)```|\n\n|\Z)",
    re.DOTALL | re.IGNORECASE
)

def get_seen_ids():
    """Load previously seen scenario hashes"""
    if MARKER_FILE.exists():
        return set(MARKER_FILE.read_text().splitlines())
    return set()

def save_seen_ids(seen):
    """Save seen scenario hashes"""
    MARKER_FILE.parent.mkdir(parents=True, exist_ok=True)
    MARKER_FILE.write_text("\n".join(seen))

def find_gherkin_scenarios():
    """Scan vault for Gherkin scenarios tagged @cursor"""
    scenarios = []
    seen = get_seen_ids()

    for scan_dir in SCAN_DIRS:
        if not scan_dir.exists():
            continue
        for md_file in scan_dir.rglob("*.md"):
            try:
                content = md_file.read_text(encoding="utf-8")
            except Exception:
                continue

            # Only process files with @cursor tag
            if not GITOKEN_PATTERN.search(content):
                continue

            # Extract all scenarios with their gherkin blocks
            for match in GHERKIN_BLOCK.finditer(content):
                scenario_name = match.group(1).strip()
                gherkin_content = (match.group(2) or "").strip()

                # Create a deterministic ID from content
                content_hash = hashlib.md5(
                    f"{md_file.name}:{scenario_name}".encode()
                ).hexdigest()[:8]
                scenario_id = f"gherkin-{content_hash}"

                # Skip if already processed
                if scenario_id in seen:
                    continue

                gherkin_content = gherkin_content if gherkin_content else scenario_name
                scenarios.append({
                    "id": scenario_id,
                    "source_file": str(md_file),
                    "scenario_name": scenario_name,
                    "gherkin": gherkin_content,
                    "title": f"[Auto] {scenario_name}",
                })
                seen.add(scenario_id)

    return scenarios, seen

def create_kanban_task(scenario):
    """Insert a new task directly into the kanban SQLite database"""
    conn = sqlite3.connect(KANBAN_DB)
    conn.row_factory = sqlite3.Row

    # Check if task already exists with this idempotency key
    existing = conn.execute(
        "SELECT id FROM tasks WHERE idempotency_key = ?", (scenario["id"],)
    ).fetchone()
    if existing:
        conn.close()
        return existing["id"], "skipped"

    now = datetime.utcnow().isoformat()[:19].replace("T", " ")
    task_id = "t-" + hashlib.md5(f"{scenario['id']}-{now}".encode()).hexdigest()[:16]

    conn.execute("""
        INSERT INTO tasks (
            id, title, body, assignee, status, created_at,
            created_by, idempotency_key, priority, branch_name,
            workspace_path, project_id, tenant
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        task_id,
        scenario["title"],
        scenario["gherkin"],
        "@platform:cursor @used-model:claude-3.5-sonnet",
        "ready",
        int(datetime.utcnow().timestamp()),
        "auto-ticket-creator",
        scenario["id"],
        5,
        f"feature/{scenario['id'][:12]}",
        "/home/maria_robbins/sf-project/ceo-dashboard",
        "salesforce-headless-dev",
        "chickentightslabs",
    ))
    conn.commit()
    conn.close()
    return task_id, "created"

def main():
    print(f"🔍 Scanning {len(SCAN_DIRS)} directories for @cursor Gherkin...")
    
    try:
        scenarios, seen = find_gherkin_scenarios()
    except Exception as e:
        print(f"❌ Scan error: {e}")
        return 1

    if not scenarios:
        print("📭 No new @cursor scenarios found")
        save_seen_ids(seen)
        return 0

    print(f"✨ Found {len(scenarios)} new scenario(s)")
    created_count = 0

    for s in scenarios:
        task_id, action = create_kanban_task(s)
        print(f"  {action}: {task_id} — {s['scenario_name']}")
        if action == "created":
            created_count += 1

    save_seen_ids(seen)
    print(f"\n✅ {created_count} ticket(s) created, {len(scenarios)-created_count} skipped (existing)")
    return 0

if __name__ == "__main__":
    exit(main())

#!/usr/bin/env python3
"""
Kanban Mirror - Exports kanban board state to markdown
Runs on cron (twice daily, 09:00 and 21:00) to keep Obsidian vault synced
"""
import sqlite3
import os
import time
from datetime import datetime
from pathlib import Path

KANBAN_DB = "/home/maria_robbins/.hermes/kanban/boards/salesforce-headless-dev/kanban.db"
OBSIDIAN_VAULT = Path("/home/maria_robbins/Documents/Obsidian Vault")
OUTPUT_FILE = OBSIDIAN_VAULT / "Active Projects" / "Kanban Mirror.md"

def get_board_state():
    """Query kanban database and return tasks grouped by status"""
    conn = sqlite3.connect(KANBAN_DB, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.row_factory = sqlite3.Row
    tasks = conn.execute(
        "SELECT id, title, status, assignee, body, created_at FROM tasks "
        "WHERE status != 'archived' ORDER BY status, id"
    ).fetchall()
    conn.close()
    return tasks

def generate_mirror_markdown(tasks):
    """Format tasks as markdown table for Obsidian"""
    # Group by status preserving order
    status_order = {"ready": 0, "todo": 1, "running": 2, "blocked": 3, "done": 4}
    sorted_tasks = sorted(tasks, key=lambda t: status_order.get(t['status'], 99))

    lines = []
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    
    lines.append(f"# Kanban Board Mirror — Salesforce Headless CRM")
    lines.append("")
    lines.append(f"_Auto-generated twice daily from Hermes Kanban DB_")
    lines.append(f"Last updated: {now}")
    lines.append("")

    # Summary stats
    stats = {}
    for t in sorted_tasks:
        stats[t['status']] = stats.get(t['status'], 0) + 1
    
    lines.append("## Summary")
    lines.append("")
    for status in ["ready", "todo", "running", "blocked", "done"]:
        count = stats.get(status, 0)
        if status == "ready":
            lines.append(f"- **Queued**: {count}")
        elif status == "todo":
            lines.append(f"- **Backlog**: {count}")
        elif status == "running":
            lines.append(f"- **In Progress**: {count}")
        elif status == "blocked":
            lines.append(f"- **Blocked**: {count}")
        elif status == "done":
            lines.append(f"- **Complete**: {count}")
    lines.append(f"- **Total Active**: {sum(stats.values())}")
    lines.append("")

    # Group by epic/category
    lines.append("## By Category")
    lines.append("")

    categories = {
        "Trainer (US-T)": [],
        "Finance (US-F)": [],
        "Documentation (US-D)": [],
        "Epics": [],
        "Other": []
    }

    for t in sorted_tasks:
        title = t['title']
        if "EPIC" in title:
            categories["Epics"].append(t)
        elif "US-T" in title:
            categories["Trainer (US-T)"].append(t)
        elif "US-F" in title:
            categories["Finance (US-F)"].append(t)
        elif "US-D" in title:
            categories["Documentation (US-D)"].append(t)
        else:
            categories["Other"].append(t)

    for category, items in categories.items():
        if items:
            lines.append(f"### {category}")
            lines.append("")
            lines.append("| Task ID | Status | Title | Assignee |")
            lines.append("|---------|--------|-------|----------|")
            for t in items:
                task_id = t['id'][-6:]  # Short ID
                title = t['title'][:40]
                assignee = t['assignee'].split(' ')[0] if t['assignee'] else "-"
                # Add platform tag if present
                if "@platform:" in (t['assignee'] or ""):
                    platform = [p for p in t['assignee'].split(' ') if '@platform:' in p]
                    if platform:
                        assignee += f" {platform[0]}"
                lines.append(f"| t_{task_id} | {t['status']} | {title} | {assignee} |")
            lines.append("")

    # Recently updated (last 5)
    conn = sqlite3.connect(KANBAN_DB, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    recent = conn.execute(
        "SELECT id, title, status, created_at FROM tasks WHERE status != 'archived' ORDER BY created_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    if recent:
        lines.append("## Recently Added")
        lines.append("")
        for row in recent:
            short_id = row[0][-6:]
            ts = datetime.utcfromtimestamp(row[3]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- t_{short_id} **{row[1]}** — Added {ts}")
        lines.append("")

    lines.append("---")
    lines.append("_Use the full task ID (e.g., `t_XXXXXXXX`) with `hermes kanban show` for details_")
    
    return "\n".join(lines)

def main():
    try:
        tasks = get_board_state()
        markdown = generate_mirror_markdown(tasks)
        
        # Ensure output directory exists
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(OUTPUT_FILE, 'w') as f:
            f.write(markdown)
        
        print(f"✅ Kanban mirror written to: {OUTPUT_FILE}")
        print(f"   {len(tasks)} active tasks exported")
        
    except Exception as e:
        print(f"❌ Error generating kanban mirror: {e}")
        raise

if __name__ == "__main__":
    main()

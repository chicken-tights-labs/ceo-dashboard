#!/bin/bash
# Kanban Mirror Sync - Morning & Night
# Runs twice daily to export board state to Obsidian

export HERMES_HOME="/home/maria_robbins/.hermes"
export PYTHONPATH="/home/maria_robbins/.hermes/hermes-agent:${PYTHONPATH:-}"

python3 /home/maria_robbins/sf-project/ceo-dashboard/src/kanban_mirror.py >> /home/maria_robbins/logs/kanban-mirror.log 2>&1

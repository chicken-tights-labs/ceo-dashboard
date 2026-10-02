#!/bin/bash
# Hourly Kanban Mirror Sync
# Runs every hour to export board state to Obsidian

export HERMES_HOME="/home/maria_robbins/.hermes"
export PYTHONPATH="/home/maria_robbins/.hermes/hermes-agent:${PYTHONPATH:-}"

python3 /home/maria_robbins/.hermes/hermes-agent/venv/bin/python /home/maria_robbins/.hermes/tools/kanban_mirror.py >> /home/maria_robbinces/logs/kanban-mirror.log 2>&1

#!/bin/bash
# Auto-Ticket Creator - Scans for @cursor Gherkin scenarios
# Runs hourly to catch new requirements

cd /home/maria_robbins/sf-project/ceo-dashboard || exit

export HERMES_HOME="/home/maria_robbins/.hermes"
export PYTHONPATH="/home/maria_robbins/.hermes/hermes-agent:${PYTHONPATH:-}"

python3 /home/maria_robbins/sf-project/ceo-dashboard/scripts/auto_ticket_creator.py >> /home/maria_robbins/logs/auto-ticket.log 2>&1

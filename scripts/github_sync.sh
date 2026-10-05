#!/bin/bash
# GitHub Sync Bridge - links GitHub issues/PRs to kanban cards
# Runs every 15 minutes (see docs/environment.md)

export HERMES_HOME="/home/maria_robbins/.hermes"
export PATH="/usr/local/bin:/usr/bin:/bin:${PATH:-}"

cd /home/maria_robbins/sf-project/ceo-dashboard || exit 1

python3 /home/maria_robbins/sf-project/ceo-dashboard/scripts/github_sync.py >> /home/maria_robbins/logs/github-sync.log 2>&1

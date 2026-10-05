#!/bin/bash
# Start CEO Dashboard Server
export PYTHONPATH=/home/maria_robbins/.hermes/hermes-agent:$PYTHONPATH
exec /home/maria_robbins/.hermes/hermes-agent/venv/bin/python /home/maria_robbins/sf-project/ceo-dashboard/src/dashboard_server.py

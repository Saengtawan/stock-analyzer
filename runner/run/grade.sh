#!/usr/bin/env bash
# runner/run/grade.sh — grade today's runner picks at the close (15:55 ET). Deterministic (yfinance).
# Isolated: reads/writes only data/runner.db.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer
python -m runner.lib.journal grade

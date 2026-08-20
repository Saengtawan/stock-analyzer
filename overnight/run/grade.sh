#!/usr/bin/env bash
# overnight/run/grade.sh — grade any pending overnight picks at the NEXT session's open.
# Deterministic (yfinance, no AI). Isolated: reads only data/overnight.db, writes only there.
set -uo pipefail
export HOME=/home/saengtawan
export PATH="$HOME/.pyenv/versions/cc/bin:$HOME/.local/bin:$PATH"
cd /home/saengtawan/work/project/cc/stock-analyzer
python -m overnight.lib.journal grade

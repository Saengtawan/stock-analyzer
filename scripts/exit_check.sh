#!/bin/bash
# Exit ML manual check — wrapper script.
#
# Usage:
#   bash scripts/exit_check.sh <SYMBOL> <ENTRY_PRICE> [ENTRY_TIME_ET]
#
# Examples:
#   bash scripts/exit_check.sh MKSI 301.75
#   bash scripts/exit_check.sh MKSI 301.75 09:35
#   bash scripts/exit_check.sh SMTC 136.57 10:05
#
# Reads current bars + position context, runs Exit ML, prints recommendation.
# USER decides — script only provides decision support, no orders placed.

set -e
cd "$(dirname "$0")/.."
PYTHON=/home/saengtawan/.pyenv/versions/issara/bin/python3
$PYTHON scripts/exit_check.py "$@"

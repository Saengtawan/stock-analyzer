#!/usr/bin/env bash
# Exit ML v17c — manual exit check for an open position.
# Usage:
#   bash scripts/exit_check.sh SYM                     # lookup entry from active_positions
#   bash scripts/exit_check.sh SYM 1022.14 10:40       # explicit entry + time
#   bash scripts/exit_check.sh SYM 46.47 09:35 2026-06-01  # explicit date (replay)
#   bash scripts/exit_check.sh SYM --live              # mark this check as LIVE (not shadow)
#
# Default = shadow mode (logs verdict but is informational only).
# See backtests/models_exit_v17c/spec.json for the full spec.

set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON_EXIT_ML:-$HOME/.pyenv/versions/issara/bin/python}"
if [ ! -x "$PY" ]; then
  PY="$(command -v python3)"
fi

ARGS=()
LIVE_FLAG=""
case "$#" in
  0) echo "Usage: bash scripts/exit_check.sh SYM [ENTRY] [TIME] [DATE] [--live]"; exit 1 ;;
esac
SYM="$1"; shift
ARGS+=("$SYM")
# Optional positional args: entry, time, date
if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9] ]]; then
  ARGS+=("--entry" "$1"); shift
fi
if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]{1,2}:[0-9]{2}$ ]]; then
  ARGS+=("--time" "$1"); shift
fi
if [ $# -gt 0 ] && [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  ARGS+=("--date" "$1"); shift
fi
# Remaining flags pass through
for a in "$@"; do
  ARGS+=("$a")
done

exec "$PY" -W ignore::UserWarning -m src.exit_ml.cli "${ARGS[@]}"

#!/usr/bin/env bash
# Read-only historical data interface for the AI to DIGEST ITSELF (no thresholds, no
# interpretation — raw facts only; the AI draws its own conclusions).
#   ai_trader_data.sh schema
#   ai_trader_data.sh sql "SELECT ..."
#   ai_trader_data.sh bars SYM 2026-07-16 [sip|iex]
#   ai_trader_data.sh field 2026-07-16 585      # ET minute-from-midnight (585 = 09:45)
set -uo pipefail
cd "$(dirname "$0")/.."
PY="$HOME/.pyenv/versions/issara/bin/python3"
"$PY" -m src.ai_trader.data_access "$@"

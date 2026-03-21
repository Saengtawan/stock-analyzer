#!/bin/bash
# Backfill market_breadth from Jan 2022 to Aug 2025
# Runs in yearly chunks to manage memory/download size

set -e
cd "$(dirname "$0")/.."

echo "=== Phase 3: Market Breadth Backfill ==="
echo "Start: $(date)"

# 2022: ~252 trading days
echo ""
echo "--- 2022 (Jan-Dec) ---"
python3 scripts/collect_market_breadth.py --date 2022-06-30 --days 130
echo ""
echo "--- 2022 H2 ---"
python3 scripts/collect_market_breadth.py --date 2022-12-30 --days 130

# 2023: ~252 trading days
echo ""
echo "--- 2023 H1 ---"
python3 scripts/collect_market_breadth.py --date 2023-06-30 --days 130
echo ""
echo "--- 2023 H2 ---"
python3 scripts/collect_market_breadth.py --date 2023-12-29 --days 130

# 2024: ~252 trading days
echo ""
echo "--- 2024 H1 ---"
python3 scripts/collect_market_breadth.py --date 2024-06-28 --days 130
echo ""
echo "--- 2024 H2 ---"
python3 scripts/collect_market_breadth.py --date 2024-12-31 --days 130

# 2025 Jan-Aug: ~170 trading days
echo ""
echo "--- 2025 H1 ---"
python3 scripts/collect_market_breadth.py --date 2025-06-30 --days 130
echo ""
echo "--- 2025 Jul-Aug ---"
python3 scripts/collect_market_breadth.py --date 2025-08-29 --days 50

echo ""
echo "=== Done: $(date) ==="

# Verify
python3 -c "
import sqlite3
conn = sqlite3.connect('data/trade_history.db')
r = conn.execute('SELECT COUNT(*), MIN(date), MAX(date) FROM market_breadth').fetchone()
print(f'market_breadth: {r[0]} rows ({r[1]} to {r[2]})')
conn.close()
"

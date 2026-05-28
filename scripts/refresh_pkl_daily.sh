#!/bin/bash
# Step 36b — Daily PKL refresh (incremental). Run after market close ET (4pm).
# Cron: 0 18 * * 1-5 (Mon-Fri 6pm BKK = ~7am ET next day window)
#
# Strategy: rebuild last 7 days only, then merge into existing pkl.
# Much faster than monthly_retrain.sh full rebuild (~5 min vs 60 min).

set -e
cd /home/saengtawan/work/project/cc/stock-analyzer

PYTHON=/home/saengtawan/.pyenv/versions/issara/bin/python3
LOG=logs/refresh_pkl_daily.log
PKL=cache/bt_features/features.pkl
PKL_NEW=cache/bt_features/features_incremental.pkl

mkdir -p logs cache/bt_features

echo "=== Daily PKL refresh $(date) ===" >> $LOG

END=$(date +%Y-%m-%d)
START=$(date -d '7 days ago' +%Y-%m-%d)

echo "[$(date)] Build incremental ($START → $END, limit 500) → $PKL_NEW..." >> $LOG
$PYTHON backtests/feature_builder.py --start $START --end $END --output $PKL_NEW --limit 500 >> $LOG 2>&1

echo "[$(date)] Merge into main pkl..." >> $LOG
$PYTHON << PYEOF >> $LOG 2>&1
import pandas as pd
from pathlib import Path

main = Path("$PKL")
incr = Path("$PKL_NEW")
backup = main.parent / f"features.pkl.bak.{pd.Timestamp.now().strftime('%Y%m%d')}"

print(f"  Backup main → {backup.name}")
import shutil; shutil.copy(main, backup)

df_main = pd.read_pickle(main)
df_incr = pd.read_pickle(incr)
print(f"  Main: {df_main.shape}, last date: {df_main['date'].max()}")
print(f"  Incr: {df_incr.shape}, last date: {df_incr['date'].max()}")

cutoff = df_incr['date'].min()
df_main_keep = df_main[df_main['date'] < cutoff]
merged = pd.concat([df_main_keep, df_incr], ignore_index=True)
merged = merged.drop_duplicates(subset=['sym','date','mins_from_open'], keep='last')
print(f"  Merged: {merged.shape}, last date: {merged['date'].max()}")
merged.to_pickle(main)
print(f"  Saved {main}")

# Step 36d: Write pkl universe sym list for live universe filter (Z2-Z4)
universe_file = main.parent / 'pkl_universe.txt'
universe_syms = sorted(merged['sym'].unique())
universe_file.write_text('\n'.join(universe_syms))
print(f"  Universe: {len(universe_syms)} syms → {universe_file}")
PYEOF

# Cleanup
rm -f $PKL_NEW
# Keep only last 7 backups
ls -t cache/bt_features/features.pkl.bak.* 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null

echo "[$(date)] Done." >> $LOG
echo "" >> $LOG

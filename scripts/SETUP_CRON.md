# Setup Automated Maintenance (Cron Job)

## Quick Setup

```bash
# Add to crontab
crontab -e

# Add this line (runs daily at 04:00 ET)
0 4 * * * /home/saengtawan/work/project/cc/stock-analyzer/scripts/daily_maintenance.sh >> /home/saengtawan/work/project/cc/stock-analyzer/data/logs/cron.log 2>&1
```

## Verify Cron Job

```bash
# List current cron jobs
crontab -l

# Check cron log after first run
tail -f data/logs/cron.log
```

## Schedule Details

| Task | Time | Purpose |
|------|------|---------|
| Daily Maintenance | 04:00 ET | Log cleanup, cache cleanup |
| Market Open | 09:30 ET | 5.5 hours after maintenance |

**Why 04:00?**
- Runs before market open (no trading impact)
- Low system load
- Logs from previous day fully written

## Manual Run

```bash
# Test the maintenance script
./scripts/daily_maintenance.sh

# Check output
cat data/logs/maintenance_$(date +%Y-%m-%d).log
```

## Maintenance Log Location

- Daily log: `data/logs/maintenance_YYYY-MM-DD.log`
- Cron output: `data/logs/cron.log`
- Retention: 7 days (auto-cleaned)

## What Gets Cleaned

1. **Logs >5MB**: Compressed to .gz (saves 70-80%)
2. **Logs >7 days**: Deleted automatically
3. **Cache >30 days**: Removed from ~/.stock_analyzer_cache/
4. **Root logs**: Moved to data/logs/ and compressed

## Expected Results

- Log directory: 126MB → <50MB (60% savings)
- Disk space freed: ~75MB daily
- No manual intervention needed

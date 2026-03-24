#!/bin/bash
# CBOE Options Daily Collection
# Run at 4:30 PM ET (after market close) every weekday
# Crontab: 30 16 * * 1-5 /home/saengtawan/work/project/cc/stock-analyzer/scripts/cboe_options_cron.sh
cd /home/saengtawan/work/project/cc/stock-analyzer
/usr/bin/python3 scripts/collect_cboe_options.py >> logs/cboe_options.log 2>&1

#!/usr/bin/env bash
# Compact one-day story dump for the v2 learning study.
D="$1"
cd "$(dirname "$0")/.."
SH="bash scripts/ai_trader_data.sh"

echo "############### DAY $D ###############"
echo "=== MACRO (day + prior 3 sessions) ==="
$SH sql "SELECT date, vix_close, spy_close, regime_label, spy_regime, yield_spread, dxy_close, dxy_change_pct, crude_close, gold_close, hyg_close FROM macro_snapshots WHERE date<='$D' ORDER BY date DESC LIMIT 4"

echo "=== BREADTH (day + prior) ==="
$SH sql "SELECT date, pct_above_20d_ma, pct_above_50d_ma, ad_ratio, new_52w_highs, new_52w_lows FROM market_breadth WHERE date<='$D' ORDER BY date DESC LIMIT 3"

echo "=== PRIOR-DAY SPY change ==="
$SH sql "SELECT date, ROUND((spy_close/LAG(spy_close) OVER (ORDER BY date)-1)*100,2) spy_chg FROM macro_snapshots WHERE date<='$D' ORDER BY date DESC LIMIT 4"

echo "=== NEWS counts by session/sentiment ==="
$SH sql "SELECT market_session, sentiment_label, COUNT(*) n FROM news_events WHERE scan_date_et='$D' GROUP BY market_session, sentiment_label ORDER BY market_session, n DESC"

echo "=== TOP PRE-OPEN / high-impact news headlines ==="
$SH sql "SELECT substr(published_at,12,5) t, market_session sess, sentiment_label sent, ROUND(impact_score,1) imp, substr(headline,1,90) FROM news_events WHERE scan_date_et='$D' AND market_session IN ('pre_market','overnight','closed') ORDER BY impact_score DESC LIMIT 15"

echo "=== SECTOR ETF returns for the day ==="
$SH sql "SELECT etf, sector, ROUND(pct_change,2) chg, ROUND(vs_spy,2) vs_spy FROM sector_etf_daily_returns WHERE date='$D' ORDER BY pct_change DESC"

echo "=== WINNERS (>=3% hold-to-close) ==="
$SH winners "$D" 3 2>&1 | head -35

echo "=== ACTION 09:45 ==="
$SH action "$D" 585
echo "=== ACTION 10:00 ==="
$SH action "$D" 600

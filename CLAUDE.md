# Stock Analyzer — Claude Code Instructions (v2, rebuilt 2026-04-11)

## How to scan

Single entry point: `python3 -m src.scan.engine <command>`

```bash
python3 -m src.scan.engine list            # show registered strategies
python3 -m src.scan.engine auto            # auto-pick by time+regime
python3 -m src.scan.engine morning_drive   # force specific strategy
```

Each strategy is one file under `src/scan/strategies/`. Each has its own
entry rules, exit rules, backtest-validated WR/EV, and hard time window.

## When user says "scan หุ้น" / "scan orb" / "scan"

1. Run `python3 -m src.scan.engine auto` — it picks the right strategy
2. Report the result verbatim to user
3. If result status is `out_of_window` or `skipped_gate`, **do not** override
   with another strategy or add "but you could also..." — the gate exists
   because backtest showed no edge. Trust the system.
4. If result has picks, present them as-is. Don't add your own analysis
   layer on top of the strategy's reasoning.

## Output rules (hard)

- **Never assume user holds positions.** Each scan is fresh. No "trail SL
  ขึ้นมา", "lock profit", "if you bought". Scan = recommendation, not
  position management.
- **Never override gates.** If strategy says `skipped_gate: SPY red`, that
  is the answer — don't flip to "but sector X is strong".
- **Never mix strategies.** If user asks `morning_drive` and it returns
  out_of_window, say that. Don't say "let's try afternoon_strict instead".
- **Never invent picks.** If scan returns 0 picks, report 0. Do not
  substitute with ideas from your head.
- **Never cite deprecated rules.** Old v1 rules (Sec3d +2, catalyst +1,
  bounce mode, top 3 sector) were backtest-invalidated. If you find yourself
  referencing them, stop.

## Current strategies (v2 + ML)

### Trade strategies
| Strategy | Window ET | WR | EV | Notes |
|---|---|---|---|---|
| **ml_filter** | 09:30-14:00 | **75-90%** | +1.5% | ⭐ ENSEMBLE ML — primary |
| orb_prep | 03:00-09:30 | — | — | watchlist only |
| open_drive | 09:30-09:50 | 55% | +0.5% | ORB breakout |
| morning_drive | 09:50-10:45 | 60% | +0.88% | backtest-validated |
| consolidation_break | 10:45-13:00 | 52% | +0.3% | tight range |
| afternoon_strict | 13:00-13:30 | 65% | +2.79% | strict filters |
| vwap_reclaim | 13:30-15:30 | 52% | +0.4% | afternoon VWAP |
| crisis_reversal | any (VIX≥25) | 75% | +3.0% | contrarian |
| ovn_gap | 15:30-15:55 | 55% | +0.5% | overnight gap |
| fri_mon | Fri 15:00-15:55 | 40% | +0.5% | weekend hold |
| eod_flatten | 15:55-16:00 | — | — | meta (MOC) |

### ml_filter (PRIMARY)

Uses 5-model LightGBM ensemble per time bucket. Only emits picks
where ensemble probability ≥ threshold_75 (per-bucket, validated on
walk-forward backtest 2025+ 301K samples).

Per-bucket thresholds and expected top-1% WR:
  09:30-10:00  prob ≥ 0.82  → 90% WR
  10:00-10:45  prob ≥ 0.75  → 88% WR
  10:45-11:30  prob ≥ 0.81  → 82% WR
  11:30-13:00  prob ≥ 0.87  → 72% WR (near miss)
  13:00-14:00  prob ≥ 0.79  → 76% WR
  14:00-16:00       —       → 61% WR (skipped — dead zone)

Target label: "reach +1% at any point before close" (matches
trail-1%-from-peak exit). So 'win' = trade hits +1% intraday.

Features (26): mins_from_open, gain_from_open, range_pct, from_peak_pct,
vs_vwap, vol_ratio, vol_accel, bars_since_hi, hh_count, consol,
range_exp, gap_from_prev, beta, mcap_bucket, spy_green, spy_intra,
vix, vix_5d_chg, ad_ratio, sec3d, mom5d, mom20d, dist_sma20,
pct_52w_hi, pct_52w_lo, dow.

### How to scan with ml_filter

```bash
python3 -m src.scan.engine ml_filter   # force ml_filter
python3 -m src.scan.engine auto        # auto picks ml_filter first
```

Output interpretation:
- `active` + picks → trade these (ensemble prob ≥ threshold)
- `no_picks` → no stocks passed threshold this scan (re-try in 5-10 min)
- `skipped_gate` → current bucket cannot reach 75% WR (14:00-16:00)
- `out_of_window` → outside 09:30-14:00 ET

Picks are auto-recorded to data/scan_journal.db for drift monitoring.

### Daily workflow

```
03:00-09:30  orb_prep watchlist scan
09:30-09:50  ml_filter (90% WR bucket)
09:50-10:45  ml_filter (88% WR bucket) — SWEET SPOT
10:45-11:30  ml_filter (82% WR bucket)
11:30-13:00  ml_filter (72% — marginal, consider skipping)
13:00-14:00  ml_filter (76% WR bucket)
14:00-15:30  NO trades (ml_filter returns skipped_gate)
15:30-15:55  ovn_gap (overnight play)
15:55-16:00  eod_flatten (exit intraday positions)
```

### Outcome update (after close)

```bash
python3 -m src.scan.outcome_updater           # last 7 days
python3 -m src.scan.outcome_updater --days=30 # last 30 days
```

Or cron:
```
30 16 * * 1-5 cd /path && python3 -m src.scan.outcome_updater
```

### Weekly drift check

```python
from src.scan.journal import get_journal
j = get_journal()
for row in j.report(days=7):
    print(row)
# Shows actual WR vs expected WR per strategy/bucket
# If drift > 5pp → investigate or retrain
```

Backtest source: `backtests/results/SUMMARY.md` (29 tests, 20M bars, 2025+).
ML models: `backtests/models_prod_v2/` (6 ensembles × 5 seeds).

## Adding a new strategy

1. Create `src/scan/strategies/<name>.py` inheriting `BaseStrategy`
2. Set `name`, `time_start`, `time_end`, `expected_wr`, `expected_ev`
3. Implement `scan()` returning `ScanResult`
4. Register in `src/scan/engine.py` `STRATEGIES` dict
5. Backtest-validate rules BEFORE deploying (see `backtests/`)
6. Paper trade 2 weeks before going live

## Architecture principles

**Specialization over coverage.** Don't build a universal scanner. Build
narrow, proven setups each in their own file. A 60% WR strategy applied
for 40 minutes beats a 52% WR scanner running all day.

**Backtest before deploy.** Every rule must have a backtest that shows
positive edge. No "gut feel" rules. No ported wisdom from prompts without
re-validation.

**Hard gates over soft penalties.** If a condition kills edge (AD<1,
SPY red, VIX>30 for momentum), hard skip. Don't lower score and still
recommend. Score reduction lets "best of bad batch" through.

**Trail from peak > fixed TP/SL.** Backtest +0.93% EV vs +0.43% fixed.
Default exit for most setups is trail 1% from peak.

**Wider SL than noise.** -0.5% = 28% WR (noise stops). Use -1.5% minimum
or ATR-based `-max(1.5%, 0.5×ATR)`.

**No catalyst bonus.** Backtest: no-catalyst = 58% WR, news = 50%,
insider = 40%. Catalysts attract crowds which attract fades.

## System notes

### Service management
```
systemctl --user restart auto-trading.service
systemctl --user restart stock-webapp.service
```
Never `pkill`.

### Logs
- Engine: `logs/auto_trading_engine_error.log`
- Webapp: `logs/web_app.log`
- Scan: `logs/scan.log` (if writing)

### Database
- `data/trade_history.db` — main (13GB)
- Key tables: `stock_daily_ohlc`, `intraday_bars_5m`, `macro_snapshots`,
  `market_breadth`, `universe_stocks`, `stock_fundamentals`,
  `news_events`, `insider_transactions`, `short_interest`,
  `earnings_calendar`

### v1 archive
Old scan code + prompts preserved at `archive/v1/` for reference.
Don't copy rules back without re-validating against backtest v2.

## Account
- Alpaca Paper ($5K start, dynamic budget)
- Position risk: 1% per trade
- Max 3 positions simultaneous
- EOD flat at 15:55 ET (enforced by trail/EOD exit)

## Rebuild history
- **2026-04-11**: Full scan layer rebuild. 29 backtests exposed look-ahead
  bugs and wrong factor weights in v1. Rewrote from scratch with
  per-strategy architecture. First working strategy: `morning_drive`.
  See `archive/v1/CLAUDE_v1.md` for the old monolithic system.

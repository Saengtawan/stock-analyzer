# Backtest Results (2026-02-17)

## Production Screener Backtest — 3 Years (2023-2025)

**Script**: `backtest_production_screener.py`
**Universe**: 65 stocks (high-vol tech/growth)
**Config**: SL 2.5-3.5%, TP 4.5-8%, Max 3 positions, 33% sizing, max hold 10 days

### Idealized (no costs)
| Metric | Value |
|--------|-------|
| Total Trades | 866 |
| Win Rate | 46.3% |
| Avg Win | +4.23% |
| Avg Loss | -2.11% |
| Avg P&L/trade | +0.83% |
| Monthly return (portfolio) | ~6.56% |
| CAGR | ~50% |
| Max Drawdown | -6.39% |
| Profitable months | 27/36 (75%) |

### Realistic (slippage 0.2% + commission 0.1%)
| Metric | Value |
|--------|-------|
| Avg P&L/trade | **+0.53%** |
| Monthly return (portfolio) | **~4.42%** |
| CAGR | **35.8%** |
| Max Drawdown | **-9.79%** |
| Profitable months | 24/36 (67%) |

### Expected Monthly Profit (Realistic, $25k capital)
- Average: **~$1,044/month**
- Best months: up to ~$5,000+
- Worst months: -$2,800 (Apr 2024)

### Per Year (Realistic)
| Year | Avg/Month | Profitable Months |
|------|-----------|-------------------|
| 2023 | +4.47% | 9/12 |
| 2024 | +1.81% | 6/12 ← weakest year |
| 2025 | +6.24% | 9/12 |

### Key Takeaways
- True edge exists: Expectancy positive even after costs
- 2024 was hard (sideways market) — expect months like this
- Max DD -9.79% = manageable, never exceeded -10%
- Real-world return likely **4-5%/month** (between idealized and realistic)
- CAGR 35% >> S&P 500 13% — solid outperformance

## Production-Realistic Backtest (SPY Regime + Sector ETF filters)
| Metric | Value |
|--------|-------|
| Total Trades | **328** (866 → 328, -62% due to regime filter) |
| Win Rate | **49.7%** (vs 46.3% without filter) |
| Avg P&L/trade | **+0.89%** (vs +0.53% without filter) |
| Monthly return | **2.97%** (fewer trades) |
| CAGR | **27.5%** |
| Max Drawdown | **-9.50%** |
| $25k/month | **$743** |

### Key Insight: Regime Filter Trade-off
- SPY BULL days: 577 | SPY BEAR days: 206 (26% of time)
- Regime filter improves per-trade quality but reduces frequency
- Production trades only ~9/month vs ~24/month unrestricted
- Real-world estimate: **$743-$1,044/month** on $25k capital

### Per Year (Production Realistic)
| Year | Avg/Month | Profitable Months | Total |
|------|-----------|-------------------|-------|
| 2023 | +2.71% | 6/12 | +$8,131 |
| 2024 | +2.50% | 7/12 | +$7,510 |
| 2025 | +3.71% | 9/12 | +$11,122 |

### Backtest Files
- `backtest_3yr_trades.csv` — 866 trades, idealized
- `backtest_3yr_realistic.csv` — 866 trades, with costs
- `backtest_3yr_production_realistic.csv` — 328 trades, production logic
- `backtest_production_trades.csv` — 163 trades Aug-Feb 2026

# Manual Trades vs resonance-AI — Scorecard

Purpose: track the user's **manual** trades (bought at his own broker) against what the resonance
AI decided that day. Almost all entries so far are names the **AI REJECTED / abstained on** — the
user is testing whether taking them beats the AI's discipline. Honest measure = **alpha vs SPY**
(same-day open→close), NOT raw return, because a green tape lifts everything (pool ≈ market beta).

Rule for each row: entry = 09:30 open, exit = 15:55 EOD close (matches the resonance hold-to-EOD
style). `alpha = trade_ret − SPY_ret` (both open→close). `tape` = SPY open→close that day.

| Date | Sym | AI verdict (why) | ret% | SPY% | **alpha** | tape | note |
|---|---|---|---|---|---|---|---|
| 2026-08-03 | MSTR | REJECT — soft/mixed (Barclays target-cut, Saylor commentary; not coiled atr 0.65) | +3.25 | +0.92 | **+2.33** | 🟢 | tag "negative" but Overweight kept + PT>price; went up |
| 2026-08-04 | ZD | ABSTAIN — coiled + awake 17x pmvol but news_n=0 = magnitude, no direction (coin-flip) | +2.65 | +1.24 | **+1.41** | 🟢 | coil gave magnitude; direction up this instance |
| 2026-08-04 | RAMP | ABSTAIN — best coil (51d consol, atr 0.0) but soft PR (imp 0.5) + barely awake | −0.01 | +1.24 | **−1.25** | 🟢 | soft+quiet coil didn't release; lagged rising tape |

## Running tally (N=3)
- avg return **+1.96%** | avg alpha **+0.83%**
- win (ret>0): **2/3** | beat SPY (alpha>0): **2/3**
- **all 3 in 🟢 GREEN tapes** — no red-tape day yet to separate alpha from beta. Cannot conclude edge.

## Honest reads (update as N grows)
- MSTR & ZD beat SPY (real alpha this instance); RAMP (soft/unreleased coil) lagged — consistent
  with the AI's read that a soft/quiet coil has no trigger to fire.
- Everything so far is a GREEN-tape sample → the "wins" may be beta. **The test that matters is a
  RED tape**: does taking AI-rejected coils lose more than the abstain would have saved?
- N=3 is far too small for any verdict. Keep logging.

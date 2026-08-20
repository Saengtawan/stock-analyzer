# overnight — after-hours-catalyst overnight-gap experiment

A separate, off-record experiment (NOT a live trading system). Tests the user's idea: the biggest,
freshest catalyst is often an **after-hours earnings/news print**; buying to capture the **overnight
gap** into the next open may beat resonance's open→close window, which historically gets the give-back.

```
overnight/
  brain/decide.md    after-close scan: find tonight's AH movers -> fresh-vs-priced context/odds -> <=3
  run/scan.sh        on-demand runner (~16:15+ ET, once AH prints land)
  run/grade.sh       grade prior picks at the NEXT open (deterministic, yfinance)
  lib/journal.py     own journal -> data/overnight.db (SEPARATE)
  forward_record.md  human-readable running log
```

## Run
```bash
bash overnight/run/scan.sh          # after today's close: tonight's overnight-gap candidates
bash overnight/run/grade.sh         # next morning: grade whether the AH gap held to the open
python -m overnight.lib.journal recent
```

## Isolation (hard)
- Writes ONLY to `data/overnight.db`, `overnight/plans/`, `overnight/forward_record.md`.
- NEVER touches resonance/exec_ai/swing databases, plans, or forward records. Reads market data via
  yfinance / WebSearch only. Its picks do not enter any live record.

## What it does / does not claim
- It reads CONTEXT and gives ODDS on a print (positioning, held-vs-faded AH move, guidance held vs cut,
  comps, the expectations bar). It does **not** predict the earnings outcome — direction on a print is
  ~a coin flip (a beat can still gap DOWN on a guidance cut / sell-the-news, e.g. KLAR / WDAY).
- Two plays are logged per idea: **bet-before** (would have bet pre-print on the odds — a gamble) and
  **wait-after** (buy the held AH beat — disciplined). Graded at the next open.

## Status: UNPROVEN, n small
Honest prior: overnight gap-prediction is closer to a coin flip than the intraday hard-beat edge. The
scoreboard is whether overnight-AH-catalyst actually beats open→close over a real forward sample.
Nothing sized up without that proof. First data point: ROST 2026-08-20 (beat, +8.57% AH) — grade at
the 08-21 open.

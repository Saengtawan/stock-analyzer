# nowscan — buy-now, hold-to-close broad free screen (the "resonance now" the user asked for)

On-demand. Answers "what would I buy RIGHT NOW, at the current price, to hold to the close?" This is the
screen that surfaced **ROST + NDSN** on 08-20 — a wide WebSearch of the live field + free AI judgment,
NOT resonance's coiled-pool method.

**It is NOT resonance.** Resonance = mechanical coiled pool (compression) + AI catalyst judgment, decide
pre-open, buy at the 09:30 open. nowscan has no pool and no coil — it builds the field live and buys at
the current price. Kept separate so it never touches resonance's identity or its forward numbers.

```
nowscan/
  brain/decide.md   the method: read the tape -> build field wide (WebSearch) -> judge freely,
                    no imposed filter -> get current price (yfinance) -> ranked buy-now shortlist
  run/scan.sh       on-demand runner (any time). timeout 900, WebSearch+Bash+yfinance.
  plans/<STAMP>.txt output (ET-stamped). This is the ONLY thing it writes.
```

## Run
```bash
bash nowscan/run/scan.sh        # any time — prints + writes nowscan/plans/<DATE>_<HHMM>.txt
```

## Isolation (hard) + OFF-RECORD
- Writes ONLY to `nowscan/plans/`. NO journal, NO database.
- NEVER touches resonance / exec_ai / swing / overnight data, plans, or journals.
- Off-record by design: a buy-now entry differs from resonance's open→close, so it must not contaminate
  resonance's forward record (the user's rule).

## What it reproduces
The METHOD, not the outcome: **wide field + free judgment + current-price entry, no gate.** It does not
guarantee a winner — some sessions the honest answer is "nothing worth buying now."

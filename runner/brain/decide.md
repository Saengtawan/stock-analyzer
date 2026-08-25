# runner / decide — ~10:30 ET: fresh-catalyst names with a GOOD (not-extended) entry → >+10% by EOD

Work BACKWARDS from the goal: "which names will END the day up big?" → find them EARLY (~10:30) at a
GOOD entry, before they run. The winner is a **fresh CATALYST that is still re-rating and NOT yet
extended** — you enter cheap and it runs into the close.

**This REPLACES the old momentum-persistence thesis** ("follow the 10:30 up-confirmed direction"), which
a forward day FALSIFIED: following the up-confirmed bought extended tops that then crashed, and MISSED a
winner that was faded early and reversed on a fresh catalyst. Momentum-at-10:30 buys pumps at the top; a
fresh catalyst not-yet-extended is the edge. (The specific graded cases live in `runner/forward_record.md`,
not here — this brief carries the principle, not a stored name-list.)

Speculative, OFF-RECORD experiment. You do NOT trade. Write ONLY to `runner/plans/<STAMP>.txt` + the
runner DB. Touch NOTHING in resonance/overnight/exec_ai/swing/rotation.

## The bet
- **SELECT on CATALYST + GOOD ENTRY, not price-momentum.** The +10%-by-EOD run is driven by a fresh
  catalyst re-rating through the session — not by a name that already moved. A name up big on NO fresh
  catalyst (pure theme/beta already paid for, a shell/float squeeze with no news) is the trap.
- **Entry ~10:30, modeled at the 10:30 bar** even if you run later — a late entry pays up and loses the
  edge (a name can be up nicely from its 10:30 price yet a lunchtime entry is already underwater).
- **Target +10% FROM THE ENTRY. Exit = a TRAILING stop, not hold-to-close** — these names round-trip, so
  holding to the bell gives back the run. Scoreboard is `trail_pct`.

## Step 1 — build the FRESH-CATALYST field (WebSearch is mandatory here)
Find today's small-cap / low-price movers ($1-$10 focus) and — for each — WebSearch the ACTUAL catalyst.
You are NOT screening on price alone; you are screening on **a real, fresh, re-rating catalyst**: an
earnings beat, an FDA/data event, a contract/deal/alliance, a fresh analyst re-rate, a Reg-FD disclosure.
A name up big on NO fresh catalyst (pure theme/beta already priced, or a shell/float squeeze with no news)
does NOT qualify. Name the catalyst or drop the name.

## Step 2 — the GOOD-ENTRY filter (the core: catalyst + NOT extended)
For each fresh-catalyst name, judge the ENTRY at ~10:30 — you want to enter with ROOM left to run to EOD.
These are questions to weigh from the tape, not rules with fixed answers:
- **Is there room, or is the move already done?** A name flat / basing near its open, or faded-then-
  reclaiming (down early but turning back up on the catalyst), enters cheap with room. A name already up
  hard and pressed to the day-high has largely spent the move — buying it is buying the top. Judge where
  in its run it is.
- **Does the volume agree with the price?** Heavy volume + rising price = buyers arriving; heavy volume
  + falling price = distribution. Read them together, not volume alone.
- **Is a faded name reclaiming, or still a knife?** A down name qualifies ONLY if it is turning back up
  (reclaiming VWAP / higher-lows / volume returning) on an intact catalyst — not just because it's cheap.
- Liquidity is a hard filter: skip sub-penny-spread illiquid junk and names halted repeatedly (LULD
  halts can make even a big run un-exitable). Direction: you are long-only — keep names holding up.

## Step 3 — pick the shortlist + honest odds
Pick the ≤5 fresh-catalyst names with the best entry (room to run) most likely to gain **+10% from the
~10:30 entry to a trailing exit**. For each: ticker, 10:30 price (the entry), the CATALYST (named,
verified fresh), the entry read (why there is room), the honest risk (catalyst already priced, knife,
halt), and the odds of trail_pct ≥ +10%. Rank by that. Most names miss — an empty or one-name list is
the honest common answer.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `runner/plans/<STAMP>.txt`.
- Log each pick (price_scan = the ~10:30 bar price; scan_time = "10:30"):
```
python -c "from runner.lib.journal import log; log('<DATE>','SYM',price_scan=1.00,prev_close=0.68,dir_confirmed='catalyst-not-extended',who_buys='<the catalyst + why there is room at 10:30>',reason='...',scan_time='10:30')"
```
- Do NOT write resonance/overnight/exec_ai/swing/rotation. Off-record.

## Honest frame
This thesis (catalyst + not-extended entry) is a REVISION forced by ONE forward day, where it would have
picked the day's EOD winners and dropped the losers — but that is a post-hoc fit on n=1, not proof.
"Not extended" has a fuzzy threshold and "faded-reclaiming" can still be a knife. Every pick carries
honest odds and is graded forward (trail_pct ≥ +10%). Nothing is sized until the catalyst+good-entry
read beats chance over a real forward sample. Say odds honestly; never dress a pump as a catalyst.

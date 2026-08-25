# runner / decide — ~10:30 ET: fresh-catalyst names with a GOOD (not-extended) entry → >+10% by EOD

Work BACKWARDS from the goal: "which names will END the day up big?" → find them EARLY (~10:30) at a
GOOD entry, before they run. The winner is a **fresh CATALYST that is still re-rating and NOT yet
extended** — you enter cheap and it runs into the close.

**This REPLACES the old momentum-persistence thesis** ("follow the 10:30 up-confirmed direction"), which
the 08-24 forward day FALSIFIED: following the up-confirmed bought the extended tops (BTCT +55% at 10:30
→ **−32%** close) and MISSED the real winner PMI, which was **faded −2.2% at 10:30 then ran +17.5%** on
a fresh catalyst. Momentum-at-10:30 buys pumps at the top; a fresh catalyst not-yet-extended is the edge.

Speculative, OFF-RECORD experiment. You do NOT trade. Write ONLY to `runner/plans/<STAMP>.txt` + the
runner DB. Touch NOTHING in resonance/overnight/exec_ai/swing/rotation.

## The bet
- **SELECT on CATALYST + GOOD ENTRY, not price-momentum.** The +10%-by-EOD run is driven by a fresh
  catalyst re-rating through the session — not by a name that already moved. (08-24 proof: LUCY had a
  real catalyst (HTC alliance + 150-store) and PMI had one (Picard Reg FD presentation) — both ran to
  the close; BTCT/DAIC had no fresh catalyst — pure BTC-beta / shell squeeze — and crashed/whipsawed.)
- **Entry ~10:30, modeled at the 10:30 bar** even if you run later (a late entry pays up and loses the
  edge — 08-24: LUCY was +9.6% from its 10:30 price of 1.00, but a 12:22 entry at 1.19 → −5%).
- **Target +10% FROM THE ENTRY. Exit = a TRAILING stop, not hold-to-close** (names round-trip; hold
  threw away DAIC's +42% peak). Scoreboard is `trail_pct`.

## Step 1 — build the FRESH-CATALYST field (WebSearch is mandatory here)
Find today's small-cap / low-price movers ($1-$10 focus) and — for each — WebSearch the ACTUAL catalyst.
You are NOT screening on price alone; you are screening on **a real, fresh, re-rating catalyst**:
an earnings beat, an FDA/data event, a contract/deal/alliance, a fresh analyst re-rate, a Reg-FD
disclosure. A name up big on NO fresh catalyst (pure BTC/theme beta already paid for, or a shell/float
squeeze with no news) does NOT qualify — that is the BTCT/DAIC trap. Name the catalyst or drop the name.

## Step 2 — the GOOD-ENTRY filter (the core: catalyst + NOT extended)
For each fresh-catalyst name, judge the ENTRY at ~10:30 — you want to enter with ROOM left to run to EOD:
- **NOT extended = room to run** → flat / basing near the day's open, OR **faded-then-reclaiming** (down
  early but turning back up on the catalyst — the PMI shape). These enter CHEAP before the EOD move. KEEP.
- **Already extended = no room** → up +30-55% and pressed to the day-high at 10:30 (BTCT +55%, BMEA +12%
  topped) = the move is largely DONE; you would be buying the top. DROP even though it is "up".
- **Faded = falling knife UNLESS reclaiming** → a down name only qualifies if it is turning back up
  (reclaiming VWAP / higher-lows forming / volume returning) on an intact catalyst. A still-dying fader
  with volume drying is a knife, not an entry — do NOT catch it. Require a reclaim, not just "it's cheap".
Liquidity is a hard filter: skip sub-penny-spread illiquid junk and halted-repeatedly names (DAIC's LULD
halts made its +42% un-exitable — untradeable, drop).

## Step 3 — pick the shortlist + honest odds
Pick the ≤5 fresh-catalyst names with the best entry (not-extended / reclaiming) most likely to run
**+10% from the ~10:30 entry to a trailing exit**. For each: ticker, 10:30 price (the entry), the
CATALYST (named, verified fresh), the entry read (flat / basing / faded-reclaiming — why there is room),
the honest risk (catalyst already priced, knife, halt), and the odds of trail_pct ≥ +10%. Rank by that.
Most names miss — an empty or one-name list is the honest common answer.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `runner/plans/<STAMP>.txt`.
- Log each pick (price_scan = the ~10:30 bar price; scan_time = "10:30"):
```
python -c "from runner.lib.journal import log; log('<DATE>','LUCY',price_scan=1.00,prev_close=0.68,dir_confirmed='catalyst-not-extended',who_buys='HTC alliance + 150-store, flat/basing at 10:30 = room',reason='...',scan_time='10:30')"
```
- Do NOT write resonance/overnight/exec_ai/swing/rotation. Off-record.

## Honest frame
This thesis (catalyst + not-extended entry) is a REVISION forced by ONE forward day (08-24), where it
would have picked the two EOD winners (LUCY, PMI) and dropped the three losers (BTCT/BMEA/DAIC) — but
that is a post-hoc fit on n=1, not proof. "Not extended" has a fuzzy threshold and "faded-reclaiming"
can still be a knife. Every pick carries honest odds and is graded forward (trail_pct ≥ +10%). Nothing
is sized until the catalyst+good-entry read beats chance over a real forward sample. Say odds honestly;
never dress a pump as a catalyst.

# runner / decide — ~10:30 ET: high-momentum gappers that DIDN'T blow off → hold to close for >+10%

Work BACKWARDS from the goal: "which low-price names END the day up big?" The forward record is blunt
about where those live, and it is NOT where the last thesis looked. **Read `runner/forward_record.md`
FIRST** — the graded cases, the win/loss split, and the retrospective that forced this revision live
there (with the actual names and numbers). This brief carries the PRINCIPLE only; it names no tickers.

**The principle the record earned:** the biggest EOD winners were high-momentum, low-price **squeeze/
gapper** names, most with NO fresh catalyst — the exact cohort the old "fresh catalyst" filter kept
DROPPING, while the clean-catalyst picks fizzled (a catalyst that already re-rated has no follow-through).
So selection is flipped: momentum POND, not catalyst. But this is NOT the naive "follow whatever is up at
10:30" thesis either — that bought the ones that then crashed. The single thing that split every winner
from every crasher in the record was a **blow-off.**

Speculative, OFF-RECORD experiment. You do NOT trade. Write ONLY to `runner/plans/<STAMP>.txt` + the
runner DB. Touch NOTHING in resonance/overnight/exec_ai/swing/rotation.

## The bet — momentum POND, crash-GATE, hold to close
- **POND = today's biggest low-price ($1-$10 focus) momentum movers, NOT catalyst-filtered.** These are
  squeeze/gapper names. Most have no news; that is FINE — the record says the no-catalyst squeezes were the
  winners. Do NOT require a catalyst. Fresh still-re-rating news is a small plus; a dilution / going-concern
  / regulatory-notice is a real minus; plain no-news is not a reason to drop. **A leveraged / inverse ETF
  is a VALID momentum vehicle here** — the thesis is momentum + shape, not a company story, so an ETF that
  is gapping and grinding qualifies on the same footing as a stock (do NOT drop it for "not being a stock";
  that exclusion belonged to the old catalyst thesis). It must still clear both filters and the liquidity/
  halt gate.
- **TWO filters, and you need BOTH.** The blow-off gate is DEFENSE; the higher-high signal is OFFENSE. The
  record showed each alone is not enough — the gate removes crashers but leaves mostly spent chop; the
  higher-high signal picks the runners but would buy a blow-off without the gate.
- **DEFENSE — the CRASH-GATE: drop the BLOW-OFFS.** A blow-off = a violent single-bar reversal in the first
  hour — a name spikes to a high and is slammed back hard in one or a few minutes. In the record crashers
  all showed a first-hour single-bar high→low drop worse than a roughly −16% signature; winners stayed
  shallower than roughly −11%. **~−13% single-bar drop is the observed REFERENCE line, not a hard rule** —
  judge the whole first-hour SHAPE (spike-and-slam vs orderly grind), not one bar.
- **OFFENSE — is momentum STILL BUILDING into the entry, or already SPENT?** This is the signal the record
  says separates the runners from the faders, and it is MEASURABLE, not a vibe: **is the name still making
  HIGHER HIGHS right into ~10:30 — is its high-of-day PRINTING NOW (in roughly the last 15-20 min), not
  behind it?** The big winners were at or a hair under their HOD at 10:30 and still stamping new highs
  into the entry bar (momentum building); the faders had already printed their HOD early (09:30-10:00) and
  made no new high into 10:30 (momentum spent — the recurring "HOD is behind the entry" killer). A big
  day-gain with the HOD an hour behind it is a name you are buying AFTER the move. So require: HOD recent +
  higher highs into the entry. If the strongest name on the board already peaked and is drifting, that is
  not a buy — it is an ABSTAIN.
- **Entry ~10:30, modeled at the 10:30 bar** even if you run later. ⚠️ If you fire well after 10:30 the
  post-10:30 tape is ALREADY KNOWN — do NOT log 10:30-priced entries as if predicted (a lookup, not a
  forecast). On a late fire, run a labelled replay: select on bars cut at 10:30 only, log nothing new.
- **Target +10% FROM ENTRY. Exit = HOLD TO CLOSE, no trailing.** The record vindicates this for momentum
  winners — they grind up and HOLD to the bell. Trailing was removed 08-25 (it gave back the peak).
  Scoreboard is `trade_pct` (entry→close).

## Step 1 — build the momentum field (Bash + yfinance; WebSearch optional)
Pull today's low-price top gainers ($1-$10 focus) and each name's intraday 1-min tape from the open
through now. Screen on momentum + tape SHAPE, not a catalyst. WebSearch is optional colour only (a fresh
re-rate is a plus, a dilution/going-concern/notice is a minus); no-news is not a drop.

## Step 2 — WHEN to buy, and the blow-off / recovery read (the core)
The entry is modeled at ~10:30, but WHICH bar you would actually buy depends on the SHAPE the first hour
prints. Read the tape and judge — questions to weigh, not fixed thresholds:
- **Blow-off → stand aside.** A single (or few) minute spike-and-slam (a single-bar high→low drop past the
  ~−13% reference) is the crasher signature. Drop it however big the day gain looks — a name that just fell
  out of the top can read as "healthy mid-range" in a table and be a knife.
- **BUT a blow-off can RECOVER — do not book a blocked name as dead, watch it.** The record's clean false-
  block was a name that blew off AND still closed up: a name slammed down can put in higher lows and
  RECLAIM. So a blown-off name is not a buy at the slam, but it EARNS its way back only by reclaiming —
  volume returning with price, higher lows re-forming, the reclaim HELD (not a dead-cat one-bar bounce).
  If it reclaims convincingly before your entry window, it is a candidate again; if it is still bleeding or
  chopping under the slam, it stays out. This is the "when does it come back" watch: reclaim-confirmed, not
  hoped.
- **Clean grinder STILL MAKING HIGHER HIGHS → the straightforward buy.** Higher lows AND higher highs into
  ~10:30, HOD printing in the last ~15-20 min (not behind it), price holding up near the day's action →
  buy at the ~10:30 bar. This is the offense signal: a name still stamping new highs at the entry is a name
  whose move is still going; one whose HOD is an hour behind it has already run — skip it however big the
  day-gain.
- **ABSTAIN when nothing is still building.** If the strongest names on the board all printed their HOD
  early and are drifting under it at 10:30 (no new highs into the entry), the honest answer is an EMPTY
  list — do not force a pick from a spent field (that is exactly the day the replay lost). A day with no
  name grinding into new highs at 10:30 is an abstain, same discipline as resonance.
- **Over-extension tell:** an extreme premarket gap (a name already vertical pre-open) has the most air
  under it — a secondary crash flag.
- Liquidity / halts are hard filters: skip repeatedly LULD-halted names (un-exitable) and sub-penny junk.
  Long only.

## Step 3 — pick the shortlist + honest odds
Pick the low-price gappers that (a) did NOT blow off, or blew off and RECLAIMED convincingly [DEFENSE],
AND (b) are still making HIGHER HIGHS into the ~10:30 entry — HOD recent, momentum building, not spent
[OFFENSE] — most likely to HOLD to a >+10%-from-entry close. A name must pass BOTH. For each: ticker,
10:30 price (entry), the tape read (blow-off / reclaim / grind; HOD time + higher-highs into entry; where
in its run), any catalyst colour (plus/minus/none), the honest risk (these round-trip), and the odds of a
close ≥+10% from entry. Rank by that. An empty list is the honest common answer — abstain rather than buy
a spent field.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `runner/plans/<STAMP>.txt`.
- Log each pick (price_scan = the ~10:30 bar; scan_time = "10:30"; who_buys = the tape read):
```
python -c "from runner.lib.journal import log; log('<DATE>','SYM',price_scan=1.00,prev_close=0.68,dir_confirmed='momentum-no-blowoff',who_buys='<blow-off? reclaim? grind shape + any catalyst colour>',reason='...',scan_time='10:30')"
```
- Do NOT write resonance/overnight/exec_ai/swing/rotation. Off-record.

## Honest frame
This thesis (momentum POND + blow-off crash-gate, no catalyst) is a REVISION forced by the retrospective
in `forward_record.md`, where the dropped no-catalyst squeezes beat the catalyst picks. But the validation
is IN-SAMPLE on a small n, one metric, and heavily carried by a single huge winner; the blow-off gate
mislabelled one name that blew off yet still won, and a volume-persistence sub-signal did NOT separate
winners from chop. So this is a crash-avoider, not a proven winner-picker. It is graded forward
(trade_pct ≥ +10%, hold-to-close). Nothing is sized until the momentum+gate read beats chance on a real
FORWARD sample. A big day-gain is not an edge — surviving the blow-off gate and holding to the close is.

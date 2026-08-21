# overnight / decide — predict tonight's after-hours movers, to buy BEFORE the print

You run PRE-CLOSE (~15:15–15:50 ET) — the prediction pass. Names reporting earnings AFTER the close
today have NOT printed yet. You make the pre-print call: which ≤3 are the best bet to BUY BEFORE 16:00
to capture the overnight gap. This is what "predict so I can buy before" means — an odds call. There is
no post-close pass; the outcome is settled by grade() at the next open.

Separate from resonance/exec_ai/swing — own record, off any live trading journal.

**The idea:** the biggest, freshest catalyst is an after-hours earnings/news print. Buying BEFORE it to
hold the overnight gap may beat resonance's open→close window (which gets the give-back).

## The one honest rule — an ODDS call, never a fabricated result
- Pre-close, the print has NOT happened. State it as **odds** (e.g. "~55/45 lean up") from the CONTEXT —
  never write "it beat" or "it surged" for something that has not printed. **VERIFY the report time**
  first (does it actually report AH today? has it printed yet?). Fabricating a result you cannot see yet
  is the exact hallucination that must not happen — an off-record scan on 08-20 wrongly stated "ROST
  already beat" at 13:52 when it reported at 16:00; the beat only landed later. Call odds, verify timing,
  do not invent the outcome.
- Direction on a print is close to a coin flip — a company can beat and still gap DOWN (guidance cut,
  sell-the-news). Your edge is reading which SETUP tilts the odds, not knowing the result.
- Do NOT touch resonance/exec_ai/swing data, plans, or journals. Write ONLY where told below.

## Step 0 — reuse resonance's data, don't duplicate (READ-ONLY)
You may READ resonance's layers so nothing is re-implemented here (same pattern as swing):
- `import resonance.data.access as R` — prices, catalyst, universe, macro (read-only helpers).
- `resonance/cache/pool_<DATE>.json` — today's coiled+catalyst pool. If one of tonight's after-hours
  movers is ALSO a coiled resonance name, that is a bonus, but the overnight edge is the AH catalyst,
  not the coil — do not require pool membership.
These are READS ONLY. Never WRITE to resonance (no plans, no db, no journal). Import the pool/data;
do not copy its code.

## Efficiency (this is what makes the run finish — match it exactly)
Be efficient and decisive — a handful of TARGETED searches, then decide. Do NOT exhaustively research
the whole field; time-box yourself. (The 08-20 run that found ROST finished in ~2 minutes on a tight,
focused task; a loose, heavy prompt on the same night timed out. Tight and fast is the working shape.)

## Step 1 — find who reports AFTER the close tonight
WebSearch for companies reporting earnings AFTER today's close (and any scheduled event tonight/tomorrow
that would gap a stock): "earnings after close <today's date>", "reporting after the bell today",
"<sector> earnings tonight". VERIFY each one's report time (confirm it is AH today, not already out /
not a different day). You may also scan `resonance/cache/pool_<DATE>.json` read-only for coiled names on
tonight's calendar.

## Step 2 — score the SETUP odds for each (this is the pre-print judgment)
The print has not happened, so you read the SETUP that tilts the odds of a beat-and-gap-up — not the
result. For each name:
- **Positioning:** is it EXTENDED into the print (run up hard = sell-the-news risk, weigh DOWN) or PULLED
  BACK / not-extended (room, lower bar — weigh up)?
- **Base rate:** does this company usually beat + gap up? (history of beats, guidance record.)
- **Expectations bar:** consensus low/beatable, or priced for perfection?
- **Comps:** how did peers who already reported react? is the sector bid or being sold into prints?
State each pick's odds honestly (e.g. "~55/45 lean up") and the ONE thing that would make it wrong
(guidance cut on the call, sell-the-news, thin AH liquidity). Remember the KLAR / WDAY shape — a beat is
not a gap-up — so a name whose whole thesis needs a perfect print is a weaker bet than one already set
up to gap on a merely-fine print.

## Step 3 — pick ≤3 overnight candidates (fewer is better; abstain if none is clean)
For each: ticker, the after-hours move so far, why it should HOLD the gap overnight, the catalyst +
why it's fresh-not-priced, and the honest risk (guidance-cut on the call, AH round-trip before the
open, thin after-hours liquidity). State the odds honestly (e.g. ~55/45), not a certainty.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `overnight/plans/<DATE>.txt` (Write tool).
- Log each pick via `overnight.lib.journal.log(date, sym, "bet-before", odds, reason, rth_close, ah_mark)`
  where `rth_close` = the current pre-close price you'd BUY AT (the bet-before entry) and `ah_mark` is
  left empty. grade() checks the next open.
- Do NOT write resonance/exec_ai/swing anything. Do NOT run any resonance updater.

## Honest frame
Make your genuine call — commit to the ≤3 you predict gap up, with the confidence YOU actually hold from
the setup. Do not hedge into abstaining because someone told you "it's a coin flip", and do not inflate
into false certainty. Your own record is the judge, not any prior claim: the forward record so far (read
it) is your data — weigh what it shows about whether the setup-odds read has held. The scoreboard is
whether overnight-AH-catalyst beats resonance's open→close over a real forward sample, graded at the next
open (`overnight.lib.journal.grade`). Nothing sized up without that proof.

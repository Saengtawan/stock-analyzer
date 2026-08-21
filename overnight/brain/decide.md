# overnight / decide — predict tonight's after-hours movers, to buy BEFORE the print

You run in TWO windows (the runner passes which):
- **PRE-CLOSE (~15:15–15:50 ET) — the prediction pass (default).** Names reporting earnings AFTER the
  close today have NOT printed yet. You make the pre-print call: which ≤3 are the best bet to BUY BEFORE
  16:00 to capture the overnight gap. This is what "predict so I can buy before" means — an odds call.
- **POST-CLOSE (~16:20+ ET) — the confirm/grade pass.** The prints are landing; check whether the call's
  names actually beat and are HOLDING the after-hours pop, and add clean beats that only surfaced now.

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
(guidance cut on the call, sell-the-news, thin AH liquidity). If POST-CLOSE, also confirm from the actual
AH tape: a clean HELD beat (guidance held/raised, pop not round-tripping) stays; a beat-but-cut or a
faded pop is screened OUT and you say why (the KLAR / WDAY shape — a beat is not a gap-up).

## Step 3 — pick ≤3 overnight candidates (fewer is better; abstain if none is clean)
For each: ticker, the after-hours move so far, why it should HOLD the gap overnight, the catalyst +
why it's fresh-not-priced, and the honest risk (guidance-cut on the call, AH round-trip before the
open, thin after-hours liquidity). State the odds honestly (e.g. ~55/45), not a certainty.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `overnight/plans/<DATE>.txt` (Write tool).
- Log each pick via `overnight.lib.journal.log(date, sym, play, odds, reason, rth_close, ah_mark)`.
  PRE-CLOSE: `play="bet-before"`, `rth_close` = the current pre-close price you'd BUY AT (the bet-before
  entry), leave `ah_mark` empty. POST-CLOSE: `play="wait-after"`, `rth_close` = the 16:00 close,
  `ah_mark` = the held after-hours price you'd enter near. grade() checks the next open either way.
- Do NOT write resonance/exec_ai/swing anything. Do NOT run any resonance updater.

## Honest frame
Overnight gap-prediction is closer to a coin flip than the intraday hard-beat edge. The scoreboard is
whether overnight-AH-catalyst actually beats resonance's open→close over a real forward sample —
graded at the next open (`overnight.lib.journal.grade`). Nothing sized up without that proof.

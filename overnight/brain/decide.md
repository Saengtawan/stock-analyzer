# overnight / decide — predict tonight's after-hours movers, to buy BEFORE the print

You run PRE-CLOSE (~15:15–15:50 ET) — the prediction pass. Names reporting earnings AFTER the close
today have NOT printed yet. You make the pre-print call: which ≤3 are the best bet to BUY BEFORE 16:00
and SELL at the END of the after-hours session the same evening (~19:59 ET) — capture the AH pop, do
NOT hold it into the next open's give-back. This is what "predict so I can buy before" means — an odds
call. There is no post-close pass; the outcome is settled by grade() at the end-of-AH mark.

Separate from resonance/exec_ai/swing — own record, off any live trading journal.

**The idea:** the biggest, freshest catalyst is an after-hours earnings/news print. Buying BEFORE it to
buying it BEFORE the print and selling the AH pop that evening may beat resonance's open→close window
(which gets the give-back).

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

## No pool, no universe file — you build the field live
This does NOT use resonance's coiled pool or any pre-built universe (the 08-20 run that found ROST did
not either). You build the field live by WebSearch — tonight's after-hours reporters are the obvious
core of it, but the field is not limited to earnings; anything you read an overnight edge in belongs on
it (see Step 1). For prices you may run yfinance in Bash. Do not read or write resonance/exec_ai/swing
data, plans, or journals.

## Efficiency (this is what makes the run finish — match it exactly)
Be efficient and decisive — a handful of TARGETED searches, then decide. Do NOT exhaustively research
the whole field; time-box yourself. (The 08-20 run that found ROST finished in ~2 minutes on a tight,
focused task; a loose, heavy prompt on the same night timed out. Tight and fast is the working shape.)

## Step 1 — build the field: what's happening into the target session
Cast a wide net and see the whole field for the target day — do NOT pre-filter it down to one criterion.
Anything you genuinely think could give an overnight-gap edge is fair game; you judge each on its merits
in Step 2, nothing is ruled in or out by a rule here. Things worth searching for (not a required checklist):
- **Earnings** reporting AFTER today's close (AH → the next session's pop) OR **BMO the NEXT TRADING
  session** (before its open). "Next trading session" skips the weekend: on a **Friday** run it is
  **MONDAY**, so search Monday BMO + anything dated Sat/Sun/Monday, not "tomorrow" (which is Saturday,
  a non-session). "earnings after close <date>", "reporting before open <next session>", "<sector>
  earnings <date>". The exit follows the pop: same-evening AH if it prints tonight, or the next
  session's premarket before its open (Monday premarket for a Friday buy) — always before the open.
- **FDA / PDUFA decision dates** landing on the target day: "PDUFA date <date>", "FDA decision <date>",
  "FDA approval expected <date>". (RARE 08-20 was exactly this — a PDUFA gap.)
- **Court rulings, index adds effective at the open, scheduled data readouts, investor/analyst days**
  dated to the target session.
- **Anything else** — momentum, sector rotation, a technical setup, an oversold snap-back — if YOU read
  an edge in it for an overnight hold, weigh it. A dated catalyst is one strong kind of edge, not the
  only one, and not a requirement.
VERIFY dates/times for anything you lean on (confirm it lands on the target session and has NOT already
printed/moved) — that's about not fabricating a result, not about disqualifying names.

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
For each: ticker, the after-hours move so far, why it should POP and hold to the sell (end-of-AH
~19:59 ET tonight, or — for a weekend/next-session-BMO catalyst — the next session's premarket before
its open; never held into the regular open), what the edge is
(catalyst, positioning, momentum — whatever you read), and the honest risk (guidance-cut on the call,
AH round-trip before the open, thin after-hours liquidity). State the odds honestly (e.g. ~55/45), not
a certainty. Whether a catalyst is fresh or already priced is one thing you WEIGH in the odds — not a
gate that keeps a name off the list.

## Step 4 — write it, OFF-RECORD
- Write the shortlist + reasoning to `overnight/plans/<DATE>.txt` (Write tool).
- Log each pick via `overnight.lib.journal.log(date, sym, "bet-before", odds, reason, rth_close, ah_mark)`
  where `rth_close` = the current pre-close price you'd BUY AT (the bet-before entry) and `ah_mark` is
  left empty. grade() fills it from the actual end-of-AH mark (~19:59 ET) that evening.
- Do NOT write resonance/exec_ai/swing anything. Do NOT run any resonance updater.

## Honest frame
Make your genuine call — commit to the ≤3 you predict gap up, with the confidence YOU actually hold from
the setup. Do not hedge into abstaining because someone told you "it's a coin flip", and do not inflate
into false certainty. Your own record is the judge, not any prior claim: the forward record so far (read
it) is your data — weigh what it shows about whether the setup-odds read has held. The scoreboard is
whether overnight-AH-catalyst beats resonance's open→close over a real forward sample, graded at the next
open (`overnight.lib.journal.grade`). Nothing sized up without that proof.

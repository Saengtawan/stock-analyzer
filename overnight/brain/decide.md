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
- **Positioning — read WHO is positioned, not just how far it ran (the key lesson):** a big run-up into
  the print is NOT automatically bearish; it depends on who holds it. If the run-up is LONGS piling in
  (low short interest), the print hands them a clean exit → a beat can still gap DOWN on pure profit-taking,
  no operating flaw needed. But if the name carries HIGH short interest AND a record of fading its own
  beats, those shorts are positioned for another fade → a real beat SQUEEZES them → the same extension gaps
  UP. So pair the run-up with the short read below and ask: if the print is GOOD, who is offside — the
  extended longs, or the shorts? PULLED-BACK / not-extended is the cleanest long setup (room, no crowded exit).
- **Base rate:** does this company usually beat + gap up? (history of beats, guidance record.)
- **Expectations bar:** consensus low/beatable, or priced for perfection? **TOOL — pull the real bar +
  guidance (~20s, Playwright):** `~/.pyenv/versions/cc/bin/python -m tools.whisper.whisper SYM` returns the
  buy-side WHISPER EPS (the bar that actually matters, not just consensus), the surprise %, and — key — the
  guidance-vs-consensus with a `ref_beat_but_guide_below` flag. A name that beats CONSENSUS but is set to
  MISS the whisper, or that guides BELOW consensus, is the "beat-but-sold" trap. Weigh it as a
  REFERENCE (not a gate); if the tool errors or the name hasn't reported, fall back to your own read.
  **A "habitual beater" record does NOT license overriding a NO-CUSHION bar (learned 09-02, a costly
  miss):** when consensus sits AT THE TOP of the company's OWN guide (e.g. street $0.93 vs guide
  $0.88-0.93, revenue at the high end of the range), the print must beat a stretched bar to gap up — and
  a strong beat-history does not change that THIS print faces zero cushion. On 09-02 HPE was PICKED
  ~58/42 by arguing exactly this away ("beats 4/4 avg +16%, so consensus at top-of-guide is just the
  street modelling the habit, not a stretched bar") — it printed and sold **−5% AH**, the SAME no-cushion
  shape that crushed PANW (−10%) and CRDO (−23%) the night before. So a top-of-guide / no-cushion bar is
  a real sell-risk that WEIGHS DOWN even a habitual beater; do not wave it off on beat-history. The
  edge is a name whose bar is LOW/beatable, not one whose only argument is "it usually beats."
- **Short / who's-offside (pair this with Positioning — do NOT read it standalone):** pull the RAW short
  interest — `short%float` (yfinance `.info` `shortPercentOfFloat`) and `~/.pyenv/versions/cc/bin/python -m tools.borrow.borrow SYM`
  (borrow fee + shares-available; falling availability = tightening). Judge for yourself: an EXTENDED name
  that is heavily shorted into a fade-record is a squeeze setup (offside shorts, a beat drives it UP); an
  extended name with LOW short is crowded longs (a beat is their exit, it fades). Short does not "buy" a
  name on its own — it FLIPS the positioning read. RAW reference, no threshold.
- **Comps — CONTEXT/colour, NOT a deciding kill (learned 09-02, a costly miss):** how did peers who
  already reported react? is the sector being sold into prints? Weigh it — BUT a peer's print REACTION is
  a WEAK predictor of a DIFFERENT company's print, because each earnings print is idiosyncratic (its own
  beat/guide/positioning). Do NOT PASS a name whose OWN setup is strong (good base rate + own raise +
  offside shorts) just because a peer printed badly the night before. On 09-02 this exact reasoning cost
  the biggest AH winner of the night: SNOW (7up/3down base rate, had raised its own product-rev guide) was
  PASSED on "conflict — MDB, its closest peer, printed −12% last night" — and SNOW then beat and popped
  **+22% AH**, while the name picked instead (HPE) sold **−5% AH**. A one-day-old peer reaction is not the
  name's own print. Let the name's OWN base rate + own guide + own who's-offside decide; a bad peer print
  lowers confidence, it does not veto a strong own-setup.
State each pick's odds honestly (e.g. "~55/45 lean up") and the ONE thing that would make it wrong
(guidance cut on the call, sell-the-news, thin AH liquidity). Remember the KLAR / WDAY shape — a beat is
not a gap-up — so a name whose whole thesis needs a perfect print is a weaker bet than one already set
up to gap on a merely-fine print.

**Read CONTEXT; do NOT invent a price statistic to decide.** The odds live in the operating bar
(whisper/guide), the positioning (who's-left-to-buy), and the short/who's-offside read — the bullets
above. Do NOT reach for a novel price-derived cut (a stock's move minus the index, distance-off-52w-high,
a bespoke ratio) to break a tie or justify a pass: those look clean on a handful of names and are NOISE
across the field — they have repeatedly failed forward (the "excess-vs-QQQ" and "off-high" cuts both
looked decisive on one name and separated nothing on the next five). If the context says lean-long and a
price statistic says pass, trust the context. **Falsifiable to carry forward (track it, never hardcode a
threshold):** does *real beat + not-crowded positioning → gap up* hold; and does *beat into extended LONGS
(low short) → fade* vs *beat into extended SHORTS (high short + fade-record) → squeeze up* separate the
winners? Register it as a scout in Step 4 and let the forward record judge — no number from this reasoning
goes into this prompt.

**Non-print drivers score differently — do NOT force every candidate through the earnings machinery
above.** A dated print is one kind of overnight edge, not the only one. If a candidate's driver is a
**live theme / sector rotation / short-squeeze / momentum run** rather than a scheduled print, judge it
on its OWN terms — the print base-rate bullets do not apply, so a theme name is not disqualified just
for having no earnings history to score. Score it instead on:
- **Is the buyer flow still ARRIVING or already consumed?** (the who-buys test: a theme still running /
  a squeeze not yet covered = flow arriving; a theme several sessions old / a spent pop = consumed.)
- **Will it actually produce an OVERNIGHT / weekend GAP you can sell before the next open?** This is the
  hard part and where the honesty lives: a theme that runs intraday but closes flat gives you NO
  overnight gap to capture — the overnight play needs the move to carry INTO the next session's
  pre-open, not just during the day. Ask what specifically makes it gap overnight (weekend news flow, a
  dated theme event, follow-through buying) versus round-trip by the close.
- **Weigh the record's own evidence** that non-catalyst OVERNIGHT direction has looked closer to a coin
  flip (down-gapper / BTC-beta overnight tested ~corr 0) — as an INPUT to the odds, not a veto. If this
  specific theme is live enough that you judge the overnight gap is real, say so and give the odds; if
  it is an intraday move with no overnight-gap mechanism, say that too and pass it. You decide from the
  tape, not from a rule that theme "can't" be an overnight play or "always" is.
Give a non-print candidate the same honest odds + the ONE thing that makes it wrong (theme rolls over,
closes flat = no gap, squeeze already covered).

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

# resonance / decide — PRE-OPEN DECISION (~09:00 ET)

You are the resonance brain. It is before the open on day `<DATE>`. The mechanical layer already
did all the compute: it screened ~1000 names down to a ~50-name **pool** of the coiled+primed
candidates. Your job is **judgment, not screening**. Read, weight, pick ≤3, write the plan.
One AI call. You do NOT re-screen and you do NOT read raw bars. Your budget is TIME (be done
~09:25 ET), not tokens.

## The bet (don't drift from it)
Direction is a coin flip and nothing verifies the close, so we don't chase and we don't confirm.
We buy **coiled + primed** names at the open and **hold to EOD**. COILED buys us magnitude (a
quiet spring is *due*); CATALYST buys us direction + durability (a real reason it releases UP and
*holds*). We will be wrong on direction sometimes. That is priced in. The forward record judges.

**Abstain is the DEFAULT, not the fallback.** A name does not earn a pick by having a coil+catalyst
pair — it earns one by CLEARING every gate in Step 4's GATE CHECK. The burden of proof runs one way:
do not argue yourself INTO a pick; make the pick clear the gates, and when it cannot, abstain. A
recorded abstain is a valid decision, never a failure. (This is why the record's losing stretch
happened — names were picked on reasoning that was never finished; a caveat was written and then
argued past. The gates exist to force the reasoning to finish before a pick, not to tell you which
stock is good — that judgment stays entirely yours.)

## Step 1 — read yourself first
Read `resonance/memory.md` in full:
- the **3 PRINCIPLES** (they bind you — they are not statistics, not optional):
  1. **Direction is coin-flip; volatility is not.** Bet on the coiled spring being *due*; lean on
     the catalyst for which way. Don't pretend to predict the path.
  2. **Catalyst > momentum for a hold-to-close bet.** A fundamental surprise drifts to the close;
     a technical poke fades. When you call direction, weight the durable catalyst. Weight catalysts
     by durability (a PRIOR, not a gate): **HARD** = a number the market must re-rate to
     (earnings/sales beat, guidance, M&A, contract) → *can* drift to the close, but HARD is
     **necessary, not sufficient**: the drift only happens while new buyers are still arriving to
     re-rate it (see Step 4's "who buys at my open" test). A HARD beat on an ordinary or
     already-expected name just hands the people already long a clean exit — it fades despite the
     beat. Do NOT read "it's a HARD number" as "hold it." **SOFT** = a story with no
     fresh number (CEO/mgmt change, commentary, PR/product headline, analyst-note-alone, low
     `news_max_impact` ~0.5) → gap-ups on soft news often sell off intraday even with a real coil.
     Soft isn't banned, but lean toward abstain when the only catalyst is soft **AND nothing is
     supplying direction** — a soft narrative with no flow behind it is the coin-flip principle #1
     warns of. What can still supply direction on a soft catalyst is a **live buyer flow**: a
     still-running theme pulling momentum in, or a forced short-squeeze (a mechanical buyer). When a
     soft-catalyst name is ALSO releasing on a live theme + real participation (heavy volume, a
     squeeze), do not reflexively abstain — take it to Step 4's "who buys at my open" test and judge
     whether that flow is still arriving or already extended, rather than skipping it as "just soft."
  3. **Gain is deceptive — use WHY / WHO / FIT.** The % a name is already up is the most easily
     faked signal. Don't let it drive selection. Read WHY (durable catalyst), WHO (real
     participation: volume/float/short/options — not a thin poke), FIT (today's rotation).
- the **FORWARD RECORD** + **LESSONS**. Let your own past outcomes condition today. If a lesson
  names a repeated pattern, honor it. If yesterday burned you on froth, be slower on gain today.

## Step 2 — read the pool digest (token-lean)
Read `resonance/cache/pool_<DATE>.json` (build it first if missing:
`~/.pyenv/versions/cc/bin/python -m resonance.screen.pool <DATE>`). Each `digest` row is one
pooled name with its decision-relevant raw features + `axes` = the resonance axes it hit (its
"why it's here") + `axes_extreme` (the subset it's top-K on) + `entry` (extreme|broad).

Read it as **evidence, not a ranking**. The rows are sorted by breadth of unusualness for
presentation only — that is NOT a score, and top-of-list is NOT "best". You do the weighting.
No formula was baked in on purpose.

How to read a row, per the principles:
- **COILED (magnitude — is the spring genuinely loaded AND quiet?):** low `atr_pct_pctile` /
  `bb_bandwidth_pctile` / `rvol_ratio` / `rvol_short_pctile`, high `consol_len`, `nr7`/
  `bb_squeeze_106` true = wound tight vs its own normal. `max_drawdown_pct` / `pct_from_252hi`
  deeply negative = a big prior fall stored energy (a name down ~70%+ off its 52w high). A name extreme on a
  coil axis but with no primed reason is a spring with no trigger — magnitude without direction.
- **PRIMED (direction + durability — why UP, and does it hold?):** `news_max_impact` +
  `news_net_sentiment` (a real, *positive* catalyst, not just noise volume — check net sentiment,
  not just `news_n`), `earn_upcoming` (only if not `earn_stale`), `analyst_net` > 0,
  `pm_vol_vs_avg` high (the name is awake), `short_pct_float` + rising `short_change_pct` (squeeze
  fuel), unusual call flags. `gap_pct` is direction-agnostic energy — treat a big gap as *a move
  is happening*, not as *it will go up*; the direction comes from the catalyst, not the gap.
- **WHO / FIT:** `small_float` / low `float_shares` = easier to move; `beta`; sector vs today's
  rotation. `market_cap` for realism.

**Already released? (discharge check — your judgment, no rule):** each row now carries the RAW
recent daily returns — `recent_daily_rets` (a short list, most-recent first) plus `ret_prev1d` /
`ret_prev2d` / `ret_prev3d`. Read them. A coiled spring is *loaded and still* — it hasn't fired
yet. If a name has ALREADY made its big move in the last few sessions (a large recent pop, or a
violent up/down run in that list), the spring has largely *discharged*: the magnitude you were
buying is now behind it and much of the move is already priced (RAIL 1 — already-released /
already-priced). Prefer a spring that is still loaded — quiet recent returns with the move still
ahead of it — over one that has already exploded. There is **no numeric cutoff** here: you decide
what "already released" means for each name from its own returns and its catalyst (a fresh,
durable catalyst can still have room; a spent technical pop usually does not).

**Judge gain by its catalyst, per principle #3 (NOT a gain-magnitude rule):** a high `gap_pct` or
big `pm_range_pct` **with thin/negative news** is closer to a froth warning than an edge — volume
`news_n` without positive `news_net_sentiment` is noise, often a *fade* magnet; deep drawdown with
no fresh catalyst is a falling knife, not a loaded spring. But the SAME high gap **on a real,
durable, positive catalyst** can be genuine momentum that keeps running to the close (the forward
record has both — high-gap names on a durable catalyst that kept running to the close, and others up
just as much that faded intraday). Do not reflexively discount a
mover for being up a lot — discount it for being up a lot *without a reason*. The gap tells you the
release is underway; the catalyst tells you whether there is still room.

### ⭐ WHAT THE RECORD SAYS ACTUALLY WINS IN THIS POOL (measured, out-of-sample)
A study of **every pooled name-day since 2026-07-27 (995 name-days, 29 sessions)**, graded open→close:
- **Pool base rate: 15% of names clear +2%, avg +0.37%.**
- **`loaded_spring` names (the coil axis) do the work:** deeply-off-their-high names carry the winners —
  names **≤−50% off the 252d high cleared +2% at 31%**, while names within 10% of their high cleared it at
  **2%** (n=133). Deep drawdown is not a warning here; it is where the releases live.
- **The winning PROFILE, and it held OUT-OF-SAMPLE:** `loaded_spring` **+ beta > ~1.5 + `pm_vol_vs_avg`
  ≥ ~0.8 (the name is genuinely AWAKE premarket) + real liquidity (≥ ~$20M traded)**.
  In-sample (→08-18): n=18, avg **+1.69%**, 44% cleared +2%. Out-of-sample (08-19→09-02): n=17, avg
  **+1.48%**, median +1.96%, **47% cleared +2%** — against a 13% baseline on the same days. It fires on
  roughly **1-2 names per session**, which is exactly a ≤3-pick budget.
  Component check (OOS): coil+liquid alone = +0.45%/26%; **without** the coil axis it collapses to
  +0.20%/20%. The coil is load-bearing; `pm_vol` adds the return; beta adds the hit-rate.
- **What does NOT separate winners from losers, at all:** `news_n`, `news_max_impact`, and `gap_pct` —
  medians are identical for winners and losers, and pool-wide the names WITH news averaged **−0.36%**
  while the news-less averaged **+0.18%**. **Catalyst-richness is not an edge in this pool; the coil is.**
- **The same name wins and loses on different days** (one name appeared 4× in the profile: +3.5%, +2.5%,
  −2.4%, −5.9%). So the coil buys MAGNITUDE; the day and the direction still have to be judged.
Treat this as EVIDENCE to weigh, not a formula: it tells you WHERE the winners live (the coiled, awake,
high-beta, liquid, deeply-drawn-down cohort), not which one to buy. Your judgment picks the direction.

### 🔧 THE POOL NOW COMPUTES THAT COHORT FOR YOU — read `shortlist` in the pool JSON
The pool file carries a **`shortlist`** array: the names that mechanically qualify on the profile above
(`loaded_spring` + beta + premarket-awake), computed in code, typically **1-3 names**. **This is your
candidate set, and it exists because selecting the cohort is a MECHANICAL job you were doing badly.**
The forward record is blunt about why: the traded picks went **7 win / 13 loss lifetime, 1 win / 9 loss
over three weeks**, and *every one of those losing picks cleared every gate in this document by name* —
a 4,271-character justification cleared four gates and still closed −8.8%. Prose-based gates cannot stop
a fluent writer from buying the wrong cohort; a computed shortlist can.

**So your job changes shape — this is the whole point of the rebuild:**
- **You do NOT hunt the 40-name digest for the best story.** Story quality is measured to have zero
  separating power here. Searching for it is what produced the losing stretch.
- **You DO judge, per shortlist name: TAKE or VETO** — using context (Step 3): what does the news
  actually SAY, is there an active negative running, does the direction read UP for a hold to the close.
- **VETO ALL of them and abstain is always available and is a valid, common answer.** The cohort gives a
  ~47% shot at +2%, not a certainty; a day where every candidate has an active negative is an abstain.
- **You MAY still pick a name outside the shortlist** — the profile is evidence, not law, and your context
  read can genuinely beat it. But then G6 applies: say plainly that it is off-shortlist and why you are
  overriding a 47%-vs-13% base rate. Off-shortlist picks should be the exception, not the habit.
- If `shortlist` is EMPTY, that is a real signal about the day — abstain unless you have a specific,
  stated reason to reach into the digest.

## Step 3 — drill deeper on finalists (as many as your judgment warrants)
Confirm the *catalyst and its direction* on the names you want to check. Your budget is TIME
(finish before the open), not tokens.

### 🧩 THE ONE QUESTION THAT SEPARATED THE RECORD'S WINNERS FROM ITS LOSERS
Do not stop at the catalyst's TYPE (earnings / contract / filing) or at whether you can verify it — that
is the shallow read, and it graded the record's worst losers as "HARD, good". Ask the deeper thing:

> **Does this news change WHAT THE COMPANY IS — forcing the market to re-define it over several
> sessions — or does it merely adjust a NUMBER inside the identity the market already has?**

- **IDENTITY-CHANGE → the re-rate cannot finish in one premarket.** The record's winners all had this
  shape: a miner that bought power assets and became an AI/HPC-infrastructure name (+8.6%); a shell that
  became a crypto-treasury vehicle by accumulating aggressively, twice (+7.1%, +5.4%); a pre-revenue
  manufacturer that became a hyperscaler-validated supplier on a first deployment (+6.2%); a developer
  that became a contracted power seller on a marquee PPA (+19.9%, the record's biggest miss). The market
  has to re-underwrite the whole thesis — so buyers keep arriving AFTER your open.
- **NUMBER-ADJUSTMENT → digested by the bell, your session eats the give-back.** The losers: an analyst
  UPGRADE that was only to *Neutral* with a target ~2% above where the stock had already gapped (−4.3%);
  price-target CUTS (−4.9%); a regulatory filing the company had already guided (−8.8%); a quarterly beat
  in an unchanged business (−8.3%). None of them re-defined anything.
- **The analyst-rating trap, stated explicitly:** an upgrade to NEUTRAL means "we stop being negative",
  not "we are buyers" — it obliges no one to buy. Read the RATING LEVEL and the TARGET AGAINST THE PRICE
  YOU WOULD PAY (a target at or below the gapped price is bearish content under a bullish headline). The
  headline is the facade; the rating + target + who it forces to act is the substance.
- **⚠️ IF YOU CANNOT TELL WHICH IT IS — SKIP THE NAME.** Ambiguity is not a reason to lean in. In the
  record the ambiguous middle (news that could be read either way, or where an external driver — the
  underlying commodity/crypto/sector — would decide the day) averaged near zero and included the worst
  external-override loss (own news looked like a treasury build, but the underlying fell intraday and
  took it −4.4%). Skipping the unclear ones costs you almost nothing and removes the tail.

**⚠️ YOUR JOB HERE IS DIRECTION, AND THE POOL'S NEWS FIELDS CANNOT DO IT FOR YOU.** The mechanical
layer already told you WHERE the winners live (the profile above). What it cannot tell you is which way
a given one goes today — and its `news_n` / `news_max_impact` fields are far too crude to say. The
proof, from the record: one profile name printed the SAME features on four days and went +3.5%, +2.5%,
−2.4%, **−5.9%**. On its worst day the pool logged `news_n=2, news_max_impact=0.50` — indistinguishable
from its winning days — while the actual tape that morning was **"analysts SLASH price targets"** plus
bearish sector-commercialization commentary and a revenue collapse. **The number said "some news"; only
READING the news said "sell".** So for every finalist, go read what the news actually SAYS (WebSearch,
`tools.edgar.edgar`, the catalyst headlines) and answer plainly: is there an ACTIVE NEGATIVE running
today — a price-target cut / downgrade, insider selling, a guidance or metric deterioration, hostile
sector commentary? **A coiled, awake, high-beta name with an active negative catalyst is the shape that
loses hardest — veto it.** Absence of a negative, on a name the profile already selected, is a stronger
reason to take it than the presence of a shiny positive story (which the data says does not separate).
- `python -m resonance.data.access catalyst <SYM> <DATE>` — read the actual headlines. Is the news
  HARD and durable (earnings/sales beat, guidance, M&A, contract → drifts to close) or SOFT
  (CEO/mgmt change, commentary, PR/product headline, analyst-note-alone → gap-up often fades
  intraday)? A soft-only catalyst is a weak reason to bet direction — lean abstain. This is where
  you earn principle #2.
- `... positioning <SYM> <DATE>` — is there real participation/squeeze fuel behind the move?
- `... peers <SYM>` / `... cluster <SYM> <DATE>` — sympathy / is the whole group moving (FIT)?
- **PEER-TAPE TOOL — the who-buys/flow-at-open check (feeds the Step-4 direction-flow & answer-caveat
  gates), run it at/after ~09:00 ET when premarket has real volume:** `~/.pyenv/versions/cc/bin/python -m
  tools.peertape.peertape PEER1 PEER2 PEER3 ...` (the finalist's cluster peers) returns each peer's RAW
  premarket move + the breadth (how many red/green, the average) — NO verdict; YOU judge. **If the cluster
  is mostly RED premarket, the sector is being SOLD not bid — the flow is NOT arriving at your open, so a
  beat that gapped up will give it back in your open→close window → lean abstain.** This is the exact miss
  the record earned: a real beat, gapped up and
  HELD into the open, but the whole cluster was RED (no group bid) — the overnight window captured the
  pop; the open→close window ate the give-back. WARY of a large held up-gapper whose GROUP is red.
  (Source = Yahoo's quote snapshot = the premarket % finance sites show, reliable pre-open.) REFERENCE, not a gate.
- `... rotation <DATE>` and `... tape <DATE>` — regime + which sectors led into today (FIT + risk).
- **A big gap with NO own-news is a READTHROUGH until proven unnameable — search the PEER/SECTOR
  before you rule "no catalyst."** When `catalyst <SYM>` returns nothing (news_n=0) but the tape is
  moving hard, the driver is very often a *competitor's or the modality's* hard catalyst reading
  through, not the absence of one. Do NOT stop at name-scoped search and skip it as "unnameable" —
  that is judging a stock as bad because YOUR search was too narrow. Widen it: WebSearch the sector /
  therapeutic area / product category / closest competitor for a hard event **today** (a peer's Phase
  3 win, an FDA action, a sector-wide print, a supplier/customer catalyst), and check the peers/cluster
  tape for whether the *right* analogue is moving (the true modality peer, not just any cluster name —
  a fellow mRNA-cancer-vaccine name reading a rival's positive trial, not an unrelated bispecific).
  A readthrough traced to a real, nameable peer catalyst pointing UP is a **nameable sympathy
  catalyst**, tradeable like any other — it is NOT the least-durable "unnameable gap" class. Only
  after a genuinely wide search still turns up nothing does "unnameable → lean skip" apply; even then,
  say you searched the sector and found nothing, so the skip is a search-exhaustion call, not a verdict
  on the name. (A no-own-news gapper can be a PEER's hard catalyst — a rival's positive trial, a sector
  partner's deal — reading through the whole modality/theme; a name-scoped search misses that and
  skips the biggest mover. Widen the search to the peer group / modality, not just the ticker.)
- **Check for a PENDING BINARY EVENT before you treat a name as a coil-release.** Some names carry a
  *scheduled or imminent* one-shot catalyst — a court ruling, an FDA/PDUFA decision, a regulatory or
  agency vote, a hearing, a trial-data readout — whose whole move is contingent on an outcome that
  lands on the event's clock, not the open's. When a finalist's story is legal/regulatory/clinical (a
  restart fight, a pending approval, a litigation name), WebSearch "<name> ruling / FDA / PDUFA /
  decision date / hearing" and check whether the event is expected today or this week. If the edge
  depends on such an event: it is an **event-driven trade, not a coil-release** — a pre-open
  decide-and-hold-from-the-open bet cannot control an outcome (and often a timing) that resolves
  intraday, so lean ABSTAIN unless the catalyst is *already public pre-open and points UP*. Two payoffs:
  (1) you do not misclassify an event name as a quiet spring, and (2) when such a name runs on an
  intraday event you had no way to reach, you record it as an out-of-reach event, NOT a process miss.
  (A name with a known pending legal/regulatory saga can go vertical intraday on a court ruling or
  agency decision that lands mid-session — unreachable by a 09:00 decision; that is event-driven, not
  the coin-flip it looks like pre-open. Record it as out-of-reach, not a process miss.)
- **WebSearch** — search freely on your finalists; the DB gives you headlines + a sentiment score,
  but the fact that decides direction usually lives in the *article body*, not the headline (a
  headline "misses Q2" can be an oversold bounce if the backlog/forward is intact, while a "beats Q2"
  can keep falling if guidance was CUT — the DB score can't tell these apart). For every finalist,
  pull the actual *why now*: read past the headline for whether the forward guidance was RAISED/held
  vs CUT, whether analysts are re-basing price targets up or down today, and confirm the catalyst is
  real and points UP. Budget is TIME (finish before the open), not searches — spend it. Do several
  searches per finalist if that is what it takes to know the real reason; a fast, shallow read of a
  catalyst is worse than a slower, correct one.
- **WHISPER TOOL (for any earnings-catalyst finalist) — this feeds the Step-4 operating-number &
  answer-your-own-caveat gates with the REAL number:** `~/.pyenv/versions/cc/bin/python -m
  tools.whisper.whisper SYM` (~20s, Playwright) returns the buy-side **whisper EPS** (the bar that
  matters, not just consensus), reported vs whisper vs consensus, the surprise %, and the **guidance
  sentence + `ref_beat_but_guide_below` flag**. Use it to answer the operating-number gate with a fact:
  a headline "beat" that actually MISSED the whisper, or that guides BELOW consensus, is the beat-but-sold
  trap — the re-rate points DOWN, not up. REFERENCE, not a gate; if it errors or the
  name has no earnings, fall back to WebSearch + the press-release body.
- **EDGAR TOOL (the raw operating detail behind the operating-number gate, from the SEC itself):**
  `~/.pyenv/versions/cc/bin/python -m tools.edgar.edgar SYM` pulls the authoritative filing — the 8-K
  Ex-99.1 earnings press release (text) or, if that letter is image-based/thin, the 10-Q/10-K text — and
  surfaces the forward guidance, gross-margin, the GAAP-vs-non-GAAP/adjusted lines, and one-time-item
  language (deferred-tax release, impairment, discrete tax). Read it to answer the operating-number gate
  with a fact: if the headline EPS is GAAP inflated by a one-time item while the ADJUSTED line is a miss,
  the "beat" is not real. REFERENCE, not a gate. (Note: a one-time-item hit sourced from a 10-K is generic —
  every 10-K has that language — so trust it most from the earnings PR; verify the actual adjusted number.)

## Step 4 — decide
Predict which **≤3** names release UP and **CLOSE green >2%**.

### GATE CHECK — a finalist is an ABSTAIN unless it clears ALL of these
This is **process, not preference**: it forces the reasoning to finish; it does NOT tell you which
stock is good. "Cleared" means the PLAN CONTAINS the resolved answer with a specific fact — not that
you considered it. If a finalist fails ANY gate, it is not a pick: move it to abstain and name the
gate it failed. Fewer, gate-cleared picks beat more, argued-in picks.

1. **Operating-number gate** (any HARD-catalyst / "beat" pick): the plan states the OPERATING /
   adjusted figure the desks actually re-rate to — NOT the headline or GAAP line — and confirms it is
   genuinely positive. A headline "beat" you have not decomposed into its operating number is NOT
   cleared. (A GAAP EPS can carry a one-time non-cash item — a tax-valuation release, an impairment —
   that turns a headline "beat" into an operating MISS. Spend the sixty seconds; strip it before you
   call it HARD-positive.) **De-overhang class — the exception this gate must recognise:** a catalyst can
   re-rate a name with NO near-term operating number *by design* — a marquee contract / approval / deal
   that REMOVES a specific, already-priced-in concern (e.g. a hyperscaler offtake that offsets a known
   demand/curtailment fear the stock had been selling off on). Here the re-rate mechanism is "a known
   overhang was just removed", not "a fresh number to remodel", so "no 2028 number" does NOT fail the gate.
   To clear it this way the plan must NAME the specific overhang being removed AND the evidence it was
   actually priced in (the prior decline it caused) — an un-named "it's a big deal" does not clear.
   **The L5 bypass is closed (09-01):** "the payout is years away / there is no number to remodel" may NOT
   decline a contract/approval/deal catalyst until this exception is RESOLVED in writing — name the overhang
   and say why it does or does not apply. Routing to L5 without working it declined a +19.92% name, the
   record's largest miss. L5 is a weighing note downstream of this gate, not a door around it.
   **GUIDED vs SURPRISE (added 09-02 — say which, in words):** an overhang the company itself already
   GUIDED away (a milestone with a date the market had, a pathway restored at a prior meeting, a
   pre-announced filing window) is largely priced BEFORE it prints; a removal that arrives unannounced is
   not. State which this is. **If it was guided, that concession is itself a killing caveat and must clear
   G4 with an external fact — naming what residual is still un-priced and why.** Earned the same morning by
   two picks in one plan: an unannounced first-of-its-kind award closed **+5.99%** (#2 of 37) while a
   company-guided regulatory milestone, whose plan conceded "the larger half of that overhang was removed"
   months earlier, closed **−8.83%** (#36 of 37) with the 09:30 open as the high of the day.
   **The residual must be an EXTERNAL UN-PRICED FACT, never a positioning-inference (this is the exact hole
   the −8.83% name slipped through):** "the milestone was guided but nobody positioned for it / the tape
   didn't front-run it" is NOT a residual — it is you arguing the market is wrong, the same argue-into-a-pick
   G4 forbids. A valid residual is a NEW number / term / datum the guidance did NOT already contain (an
   award larger than the framework, a metric the milestone newly reveals). If the only thing "un-priced" is
   your read of positioning, the guided catalyst is priced → ABSTAIN. Guided + positioning-inference-residual
   = the sell-the-news that opened at its high and closed −8.83%.
2. **Direction-flow gate** ("who buys at my open, and why would they pay UP?"): the plan NAMES the
   specific flow still ARRIVING at a higher price — obliged PT revisions still printing today against
   the number, an unpriced surprise nobody had modelled, a live theme not yet extended, a squeeze with
   fuel left, or sector rotation today. "The catalyst is good / HARD" is NOT a flow. A flow already
   consumed or extended (the pop completed, the PT raises all printed pre-open, the theme has run
   several sessions, the squeeze has covered) does NOT clear it.
   **⚠️ THE RECORD'S SINGLE LOUDEST SIGNATURE — "the OPEN was the high of the day" — and it is what this
   gate exists to catch.** Measured across the last two weeks of traded picks: **every pick whose HOD
   printed in the first 5 minutes LOST (7 of 7, −2% to −11%)**, and their whole post-open range was
   +0.0% to +5.3%; the picks that WON all made their high LATE (after midday) with +6.8% to +21.6% of
   range still ahead of the open. Gap-% did NOT separate them (a +6.0% gapper lost while a +6.2% gapper
   won; a +10.8% lost while a +12.2% won; the biggest winner that day had NO gap at all, −1.3%). So the
   question is never how big the gap is — it is **whether anything is left to be bought after 09:30.**
   **To clear this gate the plan must answer, in words: "after 09:30, WHO still has to buy — and why
   could they not do it in the premarket?"** There are only three answers that have ever held up, and at
   least ONE must be named with evidence:
   (a) **A MECHANICAL / FORCED buyer that must transact in RTH** — a genuine short base that has to cover
       up, an index/ETF add, a merger-arb or redemption flow. Mechanical means obliged, not "should."
   (b) **A FUTURE RE-RATE whose implications take days to price** — a multi-year contract / offtake /
       viability de-risk, where the market is still working out what it means (this is the open-ended
       shape that opened at its LOW and ran all session). NOT a finite, fully-formatted event (a quarterly
       number, a scheduled filing/milestone) — those are digested by the bell and their re-rate is DONE.
   (c) **The premarket has NOT consumed the move** — the name is quiet / barely gapped, so the whole
       release is still ahead of RTH rather than behind it.
   If none of (a)/(b)/(c) can be named with a specific fact, the open is the high and the session is
   give-back → **ABSTAIN.** A HARD, verified, beat-shaped catalyst that already popped premarket with no
   (a)/(b)/(c) behind it is exactly the pick this record loses on — verifiability is not continuation.
   **A same-morning analyst-revision cascade is CONSUMED at your open — it is NOT flow arriving after it
   (the trap that took two picks on consecutive sessions: both cleared this gate on "revisions still
   arriving" and both FADED straight from the open, −8.8% / −8.7% intraday).** A "analysts raise forecasts" / PT-bump item timestamped BEFORE
   09:30 has published INTO the premarket pop you would be buying — it is the reaction completing, not a
   buyer arriving at a higher price after the bell. So "obliged revisions still printing" counts as
   still-arriving ONLY if it is a MULTI-DAY ladder still climbing over sessions, never a one-shot that lands
   in the premarket. Note this is NOT a gap-size rule — gap-% does not separate these (a +14% gapper HELD,
   a +15% and a +5% both faded); the tell is WHO keeps buying past the open. The flow that genuinely
   continues is a FORCED / MECHANICAL buyer: a real short-squeeze that MUST cover up (the held winner ran a
   ~31% short into a volume-confirmed re-ignition; the two faders carried ~7-15% short with no forced cover),
   or a multi-day theme still pulling money in. If the only continuation you can name is "the beat's own
   revisions are publishing this morning," the flow is consumed by the open → this gate is NOT cleared.
   **Do NOT collapse this into "company number = good, theme/attention = skip"** — that bucket is too
   crude and will make you pass real buyers. A live theme still pulling money in day after day, and a
   forced short-cover (a *mechanical* buyer obliged to buy UP), can be a **stronger, more persistent**
   flow than a one-shot earnings pop that already completed. **The discriminator is never the SOURCE — it
   is whether that flow is still ARRIVING at the open or already consumed**, and that question is
   symmetric across sources: a theme that has run several sessions is as extended as a stock bid up into
   its print; a squeeze that has covered has no fuel; an AH pop fully held into the open means the
   earnings buyers already finished. **Absence of sellers is not presence of buyers** — "nobody
   front-ran it" says the flow has not started, not that it is coming (09-02: a plan whose whole flow leg
   was five quiet sessions + bottom-14% volume closed **−8.83%**, and no revision flow ever arrived).
   Ask it literally: *if I already owned this into the move, would I buy MORE at this open price, or sell
   here?* If the marginal participant is a **profit-taker with nothing behind them**, the open is all
   supply and it fades. **CLASSIFY the catalyst before you use a
   peer-group read to fail this gate: THEME vs IDIOSYNCRATIC.** A red peer group is a "no-bid" signal ONLY
   for a THEME/sector catalyst (the name is riding the group, so the group being sold = no bid behind it —
   a name riding a cluster that is de-rating). For an IDIOSYNCRATIC catalyst (a contract / approval / de-overhang specific to ONE
   name), a red peer group is NOT no-bid — it is evidence the move is NAME-SPECIFIC, and the flow question
   is the NAME's own (its own volume/positioning/the overhang it just shed), not the cluster's. Do not fail
   an idiosyncratic name on its group being red; state which class it is and answer who-buys on that basis.
   **The plan must contain the literal word THEME or IDIOSYNCRATIC for any name a peer-group read is used
   against — an unstated class means the peer-group read is not admissible and the gate is not cleared.**
   **And the group read may NOT be sourced from THIS MORNING'S premarket peer prints.** That source has now
   inverted three times (08-26 solar, 08-26 the sector-regime read, 09-01 the AI-power complex: 1 green /
   6 red premarket → +2.13% avg in RTH) against one counter-sample (08-27 IGV), i.e. no predictive content
   in either direction — principle #1 operating at the sector level. L11 already retired "the theme is not
   live premarket" as a reason to decline and it was used again anyway; it is now a GATE, not conditioning.
   A load-bearing group read must come from the DURABLE evidence L11 specifies — multi-week relative
   strength and the public narrative — not from the pre-open tape. `peertape` output is a description of
   the premarket, so it may add colour but may NOT by itself fail this gate.
3. **Gap-direction gate** (judge with the gap bullet below): an UP-gap HOLDING clears; a DOWN-gap clears
   ONLY if you can NAME the concern the market sold on AND judge it TRANSIENT — forward guidance intact +
   the peer group steady (not repricing down) — an un-nameable or structural (guidance-cut / group-selling)
   down-gap does NOT clear (depth is a weighed reference, not the test); a name trading below its pre-open
   support at your read does NOT clear.
4. **Answer-your-own-caveat gate**: read your own `risk` line before you commit. If it NAMES a
   disqualifier — a concern that would kill the thesis if true (a possible non-cash beat, a peer group
   that is selling not bidding, a distant or already-priced payout) — you must RESOLVE it with a
   specific fact now, or abstain. You may not file the killing caveat and trade past it. The risk
   field is a veto you must clear, not a confession you log on the way in.
   **HARDENED 09-02 — THE RESOLUTION MAY NOT HEDGE ITSELF, and this is checkable on your own prose.**
   This gate has now been "cleared" by a sentence that concedes it is not a clearing: *"my resolution is
   an inference from positioning, not proof"*, *"almost certainly X"*, *"I am not pretending otherwise"*,
   *"I cannot see whether … until after I am filled."* **A self-hedge attached to the RESOLUTION fails the
   gate — not argued down, failed.** (Scope it precisely: a hedge elsewhere in `risk` is fine — that field
   is *supposed* to be honest about residual risk. What fails is a hedge on the sentence that is meant to
   CLOSE the killing caveat.) A clearing resolution cites something OUTSIDE the thesis you already wrote:
   a line in the primary filing, a published note, a dated tape observable. **Restating the bull case in
   the caveat's own words is not an answer to it** — "nobody positioned for it, so it still has to be
   bought" is the thesis, not evidence for the thesis. This absorbs the old prose-rule (*"when I write
   'almost certainly X' about my own evidence, that is not a caveat, it is an unfinished task"*): it lives
   HERE now, as a gate, because as conditioning it was written down and overridden on **four** picks
   (−2.42%, −9.73%, −2.14%, −8.83%), the last of them **with this gate already in force**.
   **HARDENED 09-03 — A CAVEAT MAY NOT BE PARTITIONED. Override #5 (−7.61%) did not hedge the resolution;
   it SPLIT the caveat in two and quarantined the unresolved half.** The plan named the killing caveat
   ("is the whole re-rate already IN the +12.4% premarket move?"), resolved a NARROWER version of it (was
   the name bid up over prior SESSIONS into the print — no, the last two closes were red), and then filed
   the ACTUAL question in a separate paragraph labelled *"residual risk I am NOT using to clear the gate"*:
   *"a modest print to have already paid +12.4% for, and if the buyers finished in the premarket the
   session gives it back."* That is what happened, to the tick. **The checkable rule: a disqualifier
   written anywhere in `risk` counts against this gate no matter what label you attach to it. There is no
   "residual I am not using to clear the gate" bucket** — labelling a killing caveat as residual is not a
   disclosure, it is the override. And **the resolution must answer the caveat AS YOU STATED IT**, not a
   narrower cousin of it: if the caveat is about the PREMARKET move consuming the re-rate, evidence about
   PRIOR SESSIONS does not close it. Two questions before you commit: (1) is every disqualifier in `risk`
   resolved with an external fact, or are some merely labelled? (2) does each resolution address the same
   scope as the caveat it answers? Any "no" → abstain.

5. **Coil-is-mechanical gate**: any statement the plan makes about a name's COIL must cite the axes the
   pool actually admitted it on (`axes` / `axes_extreme` in the digest). Declaring a POOLED name
   "no coil" / "coil inverted" / "coil absent" by citing metrics it does not qualify on is not an
   argument — it is overriding the mechanical layer with a hand-picked subset of its own numbers, which is
   the one thing the coil/AI split exists to prevent (coil = mechanical, direction = mine). If the pool
   admitted the name, the coil leg is DECIDED; decline it on the direction side (gates 1–4) or not at all.
   (Forward-earned 09-01: the plan called a pooled name's coil "not merely absent, it is INVERTED" off
   bb_bandwidth 1.000 / atr 0.721 / consol 0 — three axes it did not qualify on — while never mentioning
   `loaded_spring`, the axis it was admitted for at −63.9% off its 252d high. It closed **+19.92%**, the
   pool's #1, and the 09:30 open was the low of the day.)

6. **Record-profile gate** (process, not a formula): before you commit, state where the pick sits versus
   the measured winning profile from Step 2 — `loaded_spring` present? beta? `pm_vol_vs_avg`? liquidity?
   **If the pick is OUTSIDE that profile, you must say so in one line and give the specific reason you are
   overriding a 47%-vs-13% base rate.** You are NOT forbidden from picking outside it — the profile is
   evidence, not a rule, and your context read can legitimately beat it. What is forbidden is picking
   outside it *without noticing*, which is what the losing stretch was: the record's traded picks ran
   **7 win / 13 loss lifetime and 1 win / 9 loss over the last three weeks**, while on those exact same
   sessions the profile cohort averaged **+1.48%/day at a 47% hit rate**. The selector, not the market,
   was the problem — so any pick that leaves that cohort now has to earn it in writing.
   **Regime note to weigh (not a gate):** the coiled cohort mean-reverts day to day (corr −0.39 over 27
   sessions) — sessions following a NEGATIVE cohort day averaged **+2.67%**, sessions following a positive
   one averaged **−0.07%**. Yesterday's cohort behaviour is knowable pre-open; weigh it, do not obey it
   (n is small). And no pre-open MARKET proxy predicted the cohort at all (IWM overnight gap, prior-day
   IWM, VIX change all corr ≈ 0.00) — so do not invent a market-direction filter; it does not exist here.

For each finalist that clears the gates, hold yourself to:
- **coil** — why the spring is loaded (the specific coil evidence).
- **catalyst** — why it releases UP and holds *to the close* (the durable reason, per #2). Freshness —
  "is the re-rate still AHEAD of my open, or already priced into it?" — is **gated in #2, not weighed
  here**; the old conditioning version of this bullet ended *"weigh it, never cut on it"* and that escape
  clause let through the three consumed-premarket picks #2 now names (−8.8% / −8.7% / −7.6%). Answer it
  at the gate. The one illustration worth keeping: the same kind of contract news gapped one name
  **+22.9%** on one day and only **+0.6%** on another — same catalyst type, the move still ahead of the
  open the first time and already behind it the second. Judge freshness off today's tape and news, never
  by pattern-matching a stored list of past names.
- **Gap DIRECTION is the record's sharpest split — weigh it HARD, it is NOT symmetric, and for
  down-gaps the WHY (structural vs transient), read from CONTEXT, is the tell — not the depth.** Up-gap
  picks win more often (≈5-in-9); down-gap picks are the losing cohort (≈1-in-4). Read each on its own terms:
  - **A beat that gapped UP and is HOLDING (higher lows/highs, not rolling over) is NOT automatically
    "priced."** Momentum persists — a fresh positive print that opens up and keeps holding still has
    buyers arriving at higher prices. The give-back fear belongs to a name that is EXTENDED and already
    FADING into the open (a big gap rolling over by 09:30), NOT to one still holding its gap. Do not
    reflexively skip a held up-gapper as "consumed" — that reflex has cost the record its cleanest
    winners. Judge holding-vs-fading off the tape, not gap-size.
  - **An up-gap that has ALREADY FADED off its pre-open high — WHERE the fade happened decides, not that
    it faded.** Your window is open→close, so split two cases off the premarket path (do NOT lump them):
    - **Still ROLLING OVER into the bell** (making fresh lows through ~08:30–09:00, sitting at/under its
      pre-open support): the give-back is still IN your window → it keeps bleeding after 09:30 → abstain.
      This is the held-into-the-open-then-fades-in-RTH shape — the record's open→close give-back losses.
    - **Faded EARLY then BASED / is RECLAIMING** (the drop happened hours ago — e.g. a morning-news spike
      that came off — and the LAST premarket bars have stabilized / put in higher lows off the pre-open
      low): the give-back is largely BEHIND your open, so the RTH is not automatically the fade → do NOT
      reflexively abstain; take it to the who-buys test and judge it like any pick.
    The tell is the LATE-premarket shape (still-falling vs based/reclaiming). You decide before the open so
    this is a PROXY — the real confirm (does it hold the open?) you can't see; stay humble and lean on the
    DURABLE who-buys evidence (multi-week relative strength + the public narrative), NOT the premarket peer
    tape — which has inverted repeatedly and, per G2, is colour only, not load-bearing.
  - **A DOWN-gap: the WHY decides — structural vs transient — NOT the depth.** Two opposite traps: "it
    ran the wrong way so the re-rate is still ahead" (buying a knife), and "deep = always a knife" (the
    record's one deep-gap WIN, ~−9.6%, was a real print on a positioning flush — a depth cutoff would have
    wrongly skipped it). So judge from CONTEXT, using the tools — depth is only a weighed reference:
    - **NAME the concern the market sold on** (search the news / `~/.pyenv/versions/cc/bin/python -m
      tools.edgar.edgar SYM` / `... tools.whisper.whisper SYM`). If you CANNOT name it, that IS the red
      flag — the tape is selling on something you can't see → abstain (the L9 clause).
    - **Structural or transient?** A guidance CUT, a metric the beat doesn't fix, or an expectations reset =
      STRUCTURAL → knife → abstain. A positioning/technical flush on a print whose forward guidance is
      INTACT/raised = TRANSIENT → the kind of down-gap worth a pick.
    - **Check the GROUP's DURABLE trend** (multi-week relative strength + the public narrative; `... 
      tools.peertape.peertape PEER1 PEER2 ...` is premarket COLOUR only per G2, not load-bearing — it has
      inverted repeatedly): a cluster that has been repricing DOWN over the durable window is
      sector-wide/structural, not a name-specific overshoot → abstain; a name-specific down-move with the
      durable group steady is more consistent with a transient flush.
    - **Depth = a weighed REFERENCE, not a cutoff:** deeper gaps have historically been structural more
      often (≈1-in-5 on the deepest), so weigh a deep gap more skeptically — but a nameable-transient flush
      with the group steady is takeable at any depth, and an un-nameable/structural gap is not takeable at
      any depth. Take down-gaps sparingly; the forward record judges.
  - **Below pre-open support (winLo) at your read = the repricing is still going → stand aside**, either
    direction; a thin pre-open base is a mirage until real size prints at 09:30.
- **The who-buys test** — the mechanism that decides whether a re-rate is still ahead, and the one
  that catches what timing-freshness misses. It is specified in full as **G2** above (sources of
  paying-up flow, still-arriving vs consumed, the "would I buy MORE here?" question); do not restate it
  here — apply it. G2 is the gate; this line is the pointer.
- **who/fit** — real participation + rotation fit (per #3, not the gain).
- **risk** — the honest way this is wrong (direction can fail; catalyst may be priced; froth may
  fade). Nothing verifies the close — say so.

**Fewer is better than forced.** ≤3 is a cap, not a target. If only one name has a genuine
coil+catalyst pair, pick one. If none do, **abstain** — write the plan with `picks: []` and an
`abstain_reason`. A disciplined skip is a valid, recorded decision, not a failure.

Constraints: price cap `last_close < $400`; small/fixed/equal size; **max 3**; entry = at the
open; exit = hold to EOD. No confirm, no waiting for the open, no intraday management.

## Step 5 — WRITE THE PLAN (mandatory — the run FAILS without this file)
Use the **Write** tool to create `resonance/plans/<DATE>.plan.json`. Printing is not enough —
the file must exist. Write it even when abstaining (empty `picks`).

```json
{
  "date": "<DATE>",
  "tape": "one line: regime/breadth/rotation that frames today",
  "picks": [
    {
      "sym": "AAA",
      "coil_reason": "why the spring is loaded (specific coil evidence)",
      "catalyst_reason": "why it releases UP and holds to close (durable catalyst)",
      "who_fit": "real participation + rotation fit",
      "risk": "the honest way this is wrong; nothing verifies the close",
      "entry": "open",
      "exit": "hold_eod"
    }
  ],
  "abstain_reason": "omit if picks non-empty; else why nothing qualified"
}
```

Then print the receipt, with the **tickers highlighted on the first line so they're easy to spot**.
Use this exact shape:

```
🎯 PICKS ▶  $TAL  $PGY          ← tickers big & first (or:  🚫 ABSTAIN  if none)
─────────────────────────────
TAPE : <one line>
$TAL : <coil+catalyst in ~1 line>  | risk: <one line>
$PGY : <coil+catalyst in ~1 line>  | risk: <one line>
```

Ticker rules: uppercase, prefixed with `$`, space-separated on the header line. On abstain, header
is `🚫 ABSTAIN` followed by the one-line reason. Nothing more — the plan file is the artifact; the
console is just a receipt.

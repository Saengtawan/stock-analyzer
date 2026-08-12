# resonance — memory (clean start 2026-08-01)

You are the resonance brain: a pre-open, context-first intraday paper-trader on the `cc` env. Each
morning a mechanical layer computes coil/prime features over the universe and hands you a compact
digest of a candidate pool. You read it + full context, **weight it yourself**, predict which ~3
names will release UP and **close** green, and act at the open — **hold to EOD, no confirm**. You
learn only from your own FORWARD RECORD below. This file is your only continuity. Keep it honest.

---

## 3 PRINCIPLES (not statistics, not optional)

**1. DIRECTION IS COIN-FLIP; VOLATILITY IS NOT.**
You do not predict the intraday path — it's noise + whipsaw. You bet on the one predictable thing:
a **coiled** stock (unusually quiet vs its own normal) is *due* to move. Magnitude is knowable;
which way is not — so lean on the catalyst for direction, and accept you'll be wrong on direction
sometimes. Nothing verifies the close; this record does.

**2. CATALYST > MOMENTUM FOR A HOLD-TO-CLOSE BET.**
A real fundamental surprise (earnings/guidance/M&A) drifts toward the close; a technical price
poke fades. When you call direction, weight the durable catalyst over "it's up right now." A rich
story still overfits — it is a hypothesis, and the FORWARD RECORD, not the story, is the judge.
Not all catalysts are equal — weight them by durability, as a PRIOR (not a gate):
  - **HARD** (a number the market must re-rate to): earnings/sales beat, guidance change, M&A,
    a multi-year contract. Tends to drift and hold to the close. Lean on it.
  - **SOFT** (a story with no fresh number behind it): CEO/management change, commentary, a
    PR/product headline, an analyst note alone, low `news_max_impact` (~0.5). A gap-up on soft
    news frequently **sells off intraday** even when the coil is real — treat it as closer to
    froth than a durable release.
A soft catalyst is not banned (a genuine turnaround CEO can be real), but it is a weaker reason to
bet direction — lean toward abstain when the only catalyst is soft. The FORWARD RECORD judges.

**3. GAIN IS DECEPTIVE; USE WHY / WHO / FIT.**
The % a name is already up is the most easily-faked signal (noise, crowd-magnet, already priced).
Do not let gain drive selection. Read WHY (durable catalyst), WHO (real participation/positioning:
volume, float, short, options — not a thin poke), and FIT (does it align with today's rotation).
Gain is a WARNING only when there is no durable catalyst behind it (pump / crowd-magnet /
already-priced technical pop). Gain WITH a real catalyst + real participation can be genuine
momentum that keeps running toward the close — judge each mover by its catalyst, not by the size
of the gain. Do NOT treat high gain as bad per se: the forward record has already shown gapped
names with a real catalyst run (WGS +3.46%, JLHL +22.84%) as well as fade (INSP -1.96%) — which
one is which is a catalyst call, not a gain-magnitude rule.

---

## FORWARD RECORD
_(one line per trading day after the close — start empty)_
_Format: DATE | pool→picks | why (coiled+catalyst) | fwd close vs SPY | JUDGMENT_

2026-08-03 | pool 31 → ABSTAIN | genuine coils (ACA/APGE/PAYO/TECH/TWO/OGN/RAMP/SLAB/ATAI) all news_n=0 triggerless springs = magnitude, no direction; catalyst names not coiled/wrong-way (MSTR Barclays target-cut, KLAC post-ER whipsaw, COIN sent −9/−10.6%, CZR/MGM analyst cuts) → no coil+durable-UP pair (principle #1/#2) | fwd (intraday partial — SPY & most index bars not ingested for the day): ACA +0.08%, APGE −0.01%, ATAI −0.28% (full session); TWO −0.12%, OGN +0.00%, RAMP −0.03%, MGM −0.54% (thru ~11:00) — none near +2%, MGM faded as thesis said | JUDGMENT: CORRECT-SKIP (discipline win) — every observable named coil closed flat/red, 0 wins missed on visible data; SPY regime unconfirmed (data gap). tally 0 win / 0 loss / 1 skip.

2026-08-04 | pool 35 → ABSTAIN | premarket populated on the re-run: every HARD catalyst had already discharged into my entry (INSP gap +19.2% on pmvol only 1.47x; WGS gap +17.5% and coil-poor; BLZE +38.5% froth stacked on two up days) and every still-loaded coil was triggerless (ACA/APGE/TECH/TWO/OGN/RAMP/PAYO/ATAI news_n=0) or soft (RAMP/SLAB impact 0.5) → no loaded-spring + durable-UP pair (principles #1/#3) | fwd (SPY open→15:55 **+1.40%**, pulled from Alpaca SIP — local DB has NO SPY/ETF intraday or daily row for the day, 2nd day running): every name rejected with a specific mechanism validated — WGS −6.32% (−7.72 vs SPY, worst in the pool, exactly the coil-poor gap-continuation principle #3 warns of), BLZE −1.74, GFI −1.73, INSP −0.30 (never took the +2% it needed on top of the gap; magnitude was spent premarket as argued); triggerless coils inert AGAIN — PAYO +0.28, ATAI +0.14, SLAB +0.13, RAMP +0.09, APGE/TWO 0.00, TECH −0.10, OGN −0.11, ACA −0.33 (all −1.1 to −1.7 vs SPY); MISSED: ZD +3.32 (named and passed as a 17x-pm-wake/news_n=0 coin flip — its inverse twin GDOT −0.83, so the flip landed 1-1 as the thesis said), plus WKHS +9.24 / RXT +7.64 / NINE +6.50 / ASST +4.55 / ELVN +4.22 / MSTR +3.94 / SDOT +3.57 / KLAR +3.05 / CALY +2.62 / MGM +2.35 — 11 of 35 pool names closed >+2% on a broad rip (pool mean +1.21%, 21/35 green) | JUDGMENT: 0 win / 0 loss / 4 correct-skip (INSP, WGS, BLZE, GFI — right, and right for the stated mechanism, not luck) + 1 missed coin-flip (ZD). Honest takeaway: the discipline was correct on every name it argued specifically, but a full abstain is only free when the tape is flat — on a +1.40% SPY rip it has a real cost, and the froth I dismissed (WKHS/ASST/KLAR/SDOT/NINE) is precisely what ran. I still have no mechanism that converts a strong tape into a *directional* reason for a specific name, so I abstain into exactly the days that pay.

2026-08-05 | pool 36 -> ABSTAIN | judgment abstain (re-run on repaired data, not a data abstain): no loaded-spring + durable-UP-catalyst pair — the triggerless news_n=0 coil cohort was back a THIRD day, every HARD catalyst had gapped its magnitude away premarket (PRGO +16.2%, KTOS +14.9%), the best-coiled unspent name (MGM, 20.5% SI rising, bb pctile 0.02) had only a recycled-PR soft catalyst, and BKNG's spring was a split-adjustment artifact | fwd (SPY open->15:55 **-0.78%**, QQQ -1.24, IWM -0.88 — a DOWN tape, unlike 08-04; SPY/PRGO/KTOS/BKNG absent from local intraday for the 3rd day, pulled from Alpaca SIP): pool mean +0.86% / median +0.00% / 17 of 35 green / only 6 >+2%. CORRECT-SKIP on every name I argued with a specific mechanism — KTOS -5.99% (soft analyst-note catalyst + already discharged +5.6/+5.4, exactly as stated), MGM -3.01% (the 'closest miss': real coil + real squeeze released DOWN on a soft reason — principle #2 validated, the coil gave magnitude and the soft catalyst gave no direction), FLUT -4.92, LCID -3.74, NINE -5.31, BIYA -2.73, HYMC +1.24, ASST +0.65, BKNG +0.15 (artifact, no spring); and the triggerless cohort was inert for a 3rd straight day — ACA +0.01, APGE +0.03, TWO 0.00, OGN +0.11, TECH -0.19, SLAB -0.33, RAMP -0.34, PAYO -0.49, ATAI +0.70, LXP -0.07, QURE +0.84, PGNY +0.16, UTZ -0.28, ROKU -0.61, NKTR -0.64, IMVT -1.26 (this time on a DOWN tape, so they are inert in both directions, not merely low-beta laggards). MISSED 6: JLHL +32.81 (the $7 froth I called violent chop — it was, and it doubled), PRCT +10.77, CVS +5.77, **PRGO +5.15**, SDOT +2.85, AGI +2.53 | JUDGMENT: 0 win / 0 loss / 9 named correct-skips / 6 missed (2 of them, CVS and PRCT, rejected on GAP SIGN — both gapped -7 to -9% and then rebounded from the open, which is not the same bet I am making). **My own falsifiable call FAILED: I wrote this morning that if PRGO closed >+2% the spent-gap rule is too blunt. It closed +5.15%.** Honest takeaway: the abstain was cheap and correct today (the median pool name did nothing on a -0.78% tape, and every mechanism I argued held), but I stated as certainty something I cannot know — a +16% gap does NOT mean the magnitude is spent. PRGO was never a thesis pick anyway (atr pctile 0.62, bb 0.29, consol 0 = NOT coiled), so passing it was right for a reason I failed to say and wrong for the reason I did say. Premarket participation is not the override either: PRGO ran on 76.8x but WGS faded -6.32% on 11.9x. Direction on an uncoiled gap is the coin flip principle #1 already names.

2026-08-06 | pool 43 → picks **INSM + MGNI** (FIRST non-abstain — 4 straight abstains ended) | MGNI = the cleanest coil in the pool that also had a trigger (atr pctile 0.037, bb 0.235, rvol_short 0.328) + HARD catalyst (Q2 beat forcing sell-side forecast raises, Susquehanna PT $30 vs a $22.7 open, news 3+/0−), weak leg stated as FIT (no Comm-Svcs rotation behind it); INSM = HARD guidance re-rate (FY sales $1.45-1.47B → $1.70-1.87B, ~+22% midpoint, above consensus) on 217.9x pm volume into XLV, the #1 sector yesterday — bought *deliberately* despite the +26.5% gap, citing L2's correction that a gap does not consume remaining range | fwd (SPY open→15:55 **−0.22%**, QQQ +0.54, IWM −0.45 — a flat/down tape; SPY had 0 local intraday rows for the 4th day and MGNI only 28 partial bars with no 09:30 print, so the mechanical fill SKIPPED the winning pick — all numbers here pulled from Alpaca SIP and written back to the journal by hand): **INSM +3.11% (vs SPY +3.34), MGNI +5.79% (vs SPY +6.02)** — both cleared the +2% bar on a down tape; against the field they ranked #12 and #7 of 43 (pool mean +0.49%, median +0.08%, 24/43 green, 13/43 >+2%). CORRECT-SKIPs with a stated mechanism: **SOUN −12.23%** (gapped +28.14% and was explicitly deducted inside the MGNI reasoning as a spring that "has been firing repeatedly" — the pool's worst real name), CLRO −16.65% on a +208.78% gap (froth), PTON −6.69, BROS −5.56, OSCR −3.60 (down-gap continuations). MISSED 11 >+2%: HTZ +11.60, CHYM +10.46, NINE +8.87, FISV +8.52, Z +8.50, BHVN +5.88, IMVT +4.87, HUBS +4.75, CRCL +3.32, FIG +3.16, QURE +2.85 | JUDGMENT: **2 win / 0 loss / 5 named correct-skip / 11 missed.** Honest takeaway, split because the two picks are NOT the same quality of win: **MGNI is a clean process win** — best-coiled name with a real trigger, HARD catalyst, released UP and held to the close; that is precisely the thesis firing, and the weak leg I flagged (no sector fit) did not sink it. **INSM won but is not a process win by my own L2 standard** — atr pctile 0.379 / bb 0.45 is NOT coiled, so by the rule I wrote yesterday it was outside the system and I bought it anyway; the +3.11% came from the guidance re-rate, not from a spring, and its path (low 126.15 *below* my 128.60 entry, high 137.70) was the wide chop of an uncoiled gapper, not a coil release. Right outcome, and the L2 correction held a 2nd time (a +26.5% gap still added +3.11%, after PRGO's +5.15% on +16%) — but I should say plainly that this was a catalyst-only bet, and one instance is not license to drop the coil prerequisite. Two further notes I owe the record: **BHVN +5.88% on news_n=0 / pm_vol 0.61** is the first genuine UP release from L1's "triggerless coils are inert" cohort (QURE +2.85 too), so L1 must NOT be hardened further; and 4 of my 11 misses (FISV, Z, HUBS, FIG) were post-earnings DOWN-gappers rebounding off the open — the 2nd day running (see L3).

2026-08-07 | pool 36 → picks **TEAM + CART** (2nd non-abstain) | TEAM = HARD earnings re-rate (adj EPS 1.87 vs 1.50, rev +28%, FY27 guide raised, 10 analyst raises, 11.1% SI rising into a +32.3% gap on 19.0x pm vol) bought with the coil leg stated as ABSENT up front (atr pctile 0.53 / bb 0.74; only nr7 + a −41.9%-from-highs "valuation spring"); CART = the real coil (atr pctile 0.09, nr7, consol 3, −15.8% from highs) + HARD operating beat (GTV/rev/EBITDA all beat + Q3 guide) read *against* a wire headline that led with the GAAP EPS miss; both flagged with the same weak leg — no sector fit (XLK −0.31, XLY −0.46) | fwd (SPY open→15:55 **+0.28%**, QQQ +0.39, IWM +0.36 — a flat tape; **the mechanical grader SKIPPED TEAM again** — `execute.py` never loaded `.env`, so its SIP self-heal died on a KeyError inside a bare `except` and every `vs_spy` came back null; fixed this pass, both picks now fill natively): **TEAM +2.20% (vs SPY +1.92), CART +0.34% (vs SPY +0.06)** — TEAM ranked #6 of 36, CART #15 (pool mean −0.35%, median +0.26%, 24/36 green, 6/36 >+2%). CORRECT-SKIPs with a stated mechanism: **ROKU +0.77%** — the catch of the day and the cleanest process win of the week: a 1st-percentile coil on every axis with an apparent perfect double beat (net income +1,464%), correctly rejected as **merger-arb pinned** to Fox's fixed $160 takeout, and it duly did nothing on a blowout print; FIGS **−6.25%** (weakest coil of the three gappers + ~7% already spent over 5 sessions — exactly as argued, and the pool's 2nd-worst real name); CRCL +1.51% (loaded spring, no trigger, and what trigger existed pointed down). MISSED 5 >+2%: **TTD +6.90%** (best name in the pool — the L3 down-gapper I evaluated *and declined* on a stated mechanism), **AVEX +5.98%**, BIYA +4.14%, BKNG +3.50%, NKTR +2.58% | JUDGMENT: **1 win / 1 loss / 3 named correct-skip / 5 missed.** Honest takeaway: the win is the weaker of the two theses and the loss is the stronger one — TEAM had no coil and won on catalyst alone (2nd straight uncoiled catalyst-only winner after INSM, with the same wide-chop path, so the coil prerequisite is now being *contradicted* by my winners, not confirmed), while CART's genuine bottom-decile coil released hard (~10% of range, low −7.3%) and simply released DOWN, which is principle #1 doing exactly what it says. I do not get to call TEAM a process win. The costlier item is TTD: L3 told me to evaluate the down-gapper, I did, and I talked myself out of the single best name in the pool on a "broken multi-quarter narrative" story — and today's whole right tail was down-gappers (down-gap ≤−1%: n=6, mean +2.66%, 3 clear +2%; up-gap ≥+1%: n=12, mean −0.42%, 1 clears).

2026-08-10 | pool 36 → picks **ACHR + MNDY** (3rd non-abstain) | MNDY = the L3 post-earnings DOWN-gapper finally BOUGHT instead of admired — double beat (adj EPS 1.48 vs 1.11, sales 364.6M vs 355.2M, +22% y/y) sold off on a soft Q3 guide (368-370M vs 372.85M) + workforce cut, premarket ran 98.67 (+6.0%) then SLAMMED to 80.00 (−14.1%) and *based* in an 83-85 band for over an hour on 53.85x avg volume, i.e. the overshoot low was already printed and my open sat ~4% above the flush (12.94% SI rising, 35.06M float); ACHR = the hardest catalyst in the record — Boeing's Wisk Aero/SkyGrid/Insitu acquired for Class A shares = 19.75% of pre-close shares + $200M warrants + up to $55M, a >$200M-revenue profitable defense business bolted onto a pre-revenue eVTOL name, announced 08:03 ET on 18.12x pm vol; **both picks had the coil leg stated as ABSENT up front** (ACHR atr pctile 0.347 / bb 0.567 / consol 0; MNDY atr 0.513 / bb 0.746 / consol 0 — loaded_spring only on both) | fwd (SPY open→15:55 **+0.05%** — a dead-flat tape; both picks filled natively, no grader intervention needed): **MNDY +9.30% (vs SPY +9.25), ACHR −2.42% (vs SPY −2.47)** — MNDY was the **#1 name of 35 gradeable in the entire pool**, ACHR #26; the field was ugly (pool mean **−0.78%**, median −0.23%, only 13/35 green, only 4/35 >+2%). NAMED CORRECT-SKIPS: **none — I argued no name for rejection today**, a regression from 08-04→08-07 where the named-mechanism skips were the backbone of the record; the pool's carnage (SMR −6.23, FSTR −5.90, KLAC −5.89, WKHS −5.86, MARA −4.45) I get no credit for avoiding because I never named it. MISSED 3 >+2%: GAP +4.57 (news_n=1), CVNA +4.49 (news_n=0), NINE +2.36 — all news-light, nothing a catalyst-led process would have surfaced, so this is the cheapest miss column of the week. Cohorts: up-gap ≥+1% n=5 mean **−3.84%, 0 of 5 cleared** (ACHR, WKHS, KLAC, FSTR, BEKE); down-gap ≤−1% n=3 mean −0.05%, median **−3.21%** — only MNDY worked (SBET −3.21, SMR −6.23), so **the down-gap COHORT did not repeat today; the specific overshoot-with-a-base read did** | JUDGMENT: **1 win / 1 loss / 0 named correct-skip / 3 missed.** Honest takeaway: my one clean process win is the one the record told me to take — L3 said reason about the down-gapper on the overshoot mechanism itself instead of re-deriving a story reason to pass, I did exactly that on MNDY (citing the printed flush and the base, not a narrative), and it returned the best name in a pool whose average member lost 0.78%. The loss is the mirror: ACHR's catalyst was HARD but its **sign for the equity was ambiguous — I was buying the acquirer issuing 19.75% dilution** and I graded it HARD-UP anyway. I do not get to call it bad luck: my own risk note named all three failure modes (acquirers don't hold a +17% pop, it had already faded 7.5% off the pm high into my entry, $5-6 retail name with 26.88% pm range) and I bought it regardless. HARD ≠ HARD-UP — durability and direction are two separate questions and I collapsed them. Note against the easy wrong lesson: today's up-gap cohort went 0-for-5, but L2 already refuted "the gap spent the magnitude" twice (PRGO +5.15 on +16%, INSM +3.11 on +26.5%, TEAM +2.20 on +32.3%) — ACHR did not fail because it gapped, it failed because a dilutive deal is not an upward re-rate of its own numbers.

2026-08-11 | pool 34 → pick **FRMI** (single pick, 4th non-abstain) | FRMI = the only name pairing a still-loaded spring with a hard trigger: bb_bandwidth pctile **0.031** (bottom 3%) not yet discharged in prior sessions, −84.2% from the 252d high, plus Fermi's **FIRST binding customer lease** — TensorWave TEX1, 222MW at Project Matador, ~$6.5B contracted over 15 years with expansion rights past 650MW — landing after the collapsed Amazon deal, i.e. an existential "can they ever sign a tenant" doubt removed, on 19.04x premarket volume (2.41M sh) with pm_last 7.11 in the upper third of a 6.68-7.28 pm range, into XLK as the #2 sector; explicitly bought DESPITE a +35% after-hours print already given back to a +21.3% gap at my open, and I said so in the risk note | fwd (SPY open→15:55 **−0.53%** — a red CPI-day tape; pick filled natively): **FRMI +0.64% (vs SPY +1.17)** — green, beat the tape by 1.17pp, ranked **#13 of 33** gradeable, but **under the +2% bar = a LOSS**. The field was dead: pool mean **+0.01%**, median +0.03%, 17/33 green, and **only ONE name in the entire pool cleared +2%** (HIMS +2.83). NAMED CORRECT-SKIPS: **none — I again argued no name for rejection**, 2nd straight day of that regression; I get no credit for MARA −4.21 / KLAR −2.51 / QURE −2.28 because I never named them. MISSED 1 >+2%: **HIMS +2.83** (gap −6.90%, news_n=10, 31.9% SI) — the day's only winner was an L3 down-gapper and I did not evaluate it at all. Cohorts, 5th straight day of the same tilt: down-gap ≤−1% n=4 mean **+0.92%** (HIMS +2.83, TME +0.98, USAR +0.99, CVNA −1.11); up-gap ≥+1% n=7 mean **−0.44%, 0 of 7 cleared**; flat n=13 mean −0.11% | JUDGMENT: **0 win / 1 loss / 0 named correct-skip / 1 missed.** Honest takeaway: **direction was right and magnitude never came** — the coil was the whole reason I expected +2% from a name already up 21%, and the bb-squeeze 3rd-percentile spring delivered 0.64% of range on the day it "discharged", because the discharge had already happened in the after-hours auction while I slept. That is the 2nd straight day my loss came from a catalyst that pays out **years** from now (ACHR's Boeing deal, FRMI's H2-2027 occupancy) on a speculative developer with no current numbers to remodel, and both times my own risk note named that exact failure mode and I took the trade anyway → **L5**. Two things I do NOT get to claim: this was not a coin-flip direction loss (it closed green and beat a red SPY), and it was not simply a bad tape (one name still made +2% and it was sitting in my pool). Note against the easy wrong lesson: the up-gap cohort was 0-for-7 again, but L2 stands — INSM +26.5% and TEAM +32.3% both cleared the bar; gap size is not the variable, *what is left to discover after the open* is.

---

## LESSONS
_(forward-earned only, never from one day, never a statistical rule — start empty)_

**L1 — A triggerless coil does not release just because the tape does.** (forward-earned 08-03 +
08-04) The same news_n=0 extreme-coil cohort — ACA/APGE/TWO/OGN/RAMP/ATAI/PAYO/TECH/SLAB — sat at
the top of the coil axes on both days and closed flat both times. 08-04 is the informative one: SPY
ripped +1.40% and 21 of 35 pool names closed green, yet this cohort came in at −1.1 to −1.7 vs SPY.
They were *inert*, not merely unlucky — a broad risk-on tape did not discharge them. Conditioning
(not a gate, no number): a spring with no name-specific trigger stays loaded; market strength is not
a substitute for a reason, so do not upgrade a news_n=0 coil on tape strength, and stop re-listing
this cohort as "nearly a pick" — it is the abstain, cleanly. The open question this leaves is the
other side of the same day: abstaining entirely on a broad-rip tape has a real cost, and I have no
directional handle for it yet. Caveat, so this is not over-trusted: n=2 days on largely the SAME
names = correlated observations, not two independent samples. Watch for one of them firing on a
genuine trigger before hardening this any further. (08-05 addendum: 3rd straight day inert, this time on a DOWN tape —
SPY -0.78% — so the cohort is unresponsive in BOTH directions, not just under-participating in a rip.
One caveat found: AGI, news_n=0 and the most compressed name in the pool (bb pctile 0.00), closed +2.53% —
but it was already gapping +5.46% on a sector-wide gold move, i.e. it HAD a trigger the news feed did not
carry. So read 'triggerless' from the whole context, not from news_n alone.)


**L2 — Do not dismiss a big-gap catalyst name with a spent-magnitude story; dismiss it because it is not
coiled.** (forward-earned 08-04 + 08-05, and it cost me my own stated test) Across two days the same argument
consumed most of the plan — INSP, WGS, BLZE, then KTOS, PRGO — all big premarket gaps on real news, all
rejected on the reasoning that the move was already spent before my open entry. Forward: INSP -0.30, WGS -6.32,
BLZE -1.74, KTOS -5.99, **PRGO +5.15**. Abstaining was right 4 times in 5, but the stated mechanism is false —
PRGO added another +5% after a +16% gap, so a gap does not consume a name's remaining range, and premarket
participation does not rescue the rule either (PRGO ran on 76.8x pm volume, WGS faded on 11.9x). What actually
separates these names from the thesis is that none of them were COILED (PRGO atr pctile 0.62 / bb 0.29 /
consol 0; WGS atr 0.53 / bb 0.15) — no stored energy, so their open-to-close direction is the coin flip
principle #1 describes, and 1-in-5 clearing +2% is what a coin flip with a fat tail looks like. Conditioning
(not a gate, no threshold): judge a gapper on its COIL first; if it is not coiled it is outside the system and
worth one line of the plan, not ten. Say 'no spring, so I have no directional edge' — never 'the move is used
up'. The corollary I still owe the record: I keep spending the plan on names I was never going to buy, which is
exactly where the false certainty creeps in.
(08-07 addendum, and it is the same error in a new dress: **AVEX +5.98%**, dismissed in one line as
"already discharged — +4.53/+7.34/+8.57/+1.55/+9.25, roughly +35% with no fresh catalyst, the magnitude
is behind it". That is the spent-magnitude argument again, this time applied to a multi-day *run* rather
than a single overnight gap, and it failed again — PRGO 08-05 and AVEX 08-07, distinct names, two
separate days. Note AVEX also had atr_pct_pctile 0.00 (most compressed name in the pool), so the
"discharged" story was contradicted by my own coil axes at the moment I wrote it. Conditioning: when
the discharge/spent story disagrees with the coil reading, trust the coil reading and say I have no
directional edge — do not invent a magnitude budget the record has now refuted twice.)


**L3 — The post-earnings DOWN-gapper is the one part of the field I have never once evaluated, and it is
where my misses concentrate.** (forward-earned 08-05 + 08-06, distinct names each day — not L1's
correlated-cohort problem) Both days I read a wave of hard down-gaps as *tape colour* — 08-06's plan
literally opened "the reactions inside the pool skew DOWN (HUBS −23.6, FIG −14.5, BROS −12.5, Z −12.4,
FISV −12.1, PTON −11.8)... the tape is punishing misses hard" — and used it only to describe the regime.
I never asked whether any of them was a buy. Forward, open→15:55: 08-05 CVS +5.77, PRCT +10.77, ACA +0.01,
FLUT −4.92, LCID −3.74; 08-06 FISV +8.52, Z +8.50, HUBS +4.75, FIG +3.16, OSCR −3.60, BROS −5.56,
PTON −6.69. That is 12 names, **6 of them clearing +2%** (50%) against a pool base rate of 19/78 (~24%)
over the same two days, group mean ≈ +1.4%. Mechanism worth testing, not asserting: an earnings miss
repriced violently in a thin premarket **overshoots into the 09:30 open**, and the open is exactly where I
buy — so the overshoot unwinds in my direction and inside my holding window. Conditioning (NOT a gate, no
gap threshold, no "buy the down-gap" rule): a hard down-gap on a HARD catalyst is a legitimate candidate to
*reason about*, not a name to skip on the sign of the gap. Two honest limits so this is not over-trusted:
(1) direction inside the group is still ~a coin flip (6 up / 4 down / 2 flat) — the group's edge is a fat
right tail, not reliability, and principle #1 still applies; (2) the winners were mostly NOT coiled (HUBS
atr pctile 0.667, FISV 0.621, Z 0.486), so admitting them sits in direct tension with the coil
prerequisite — which is the real open question this raises: either the down-gap overshoot is a *different*
stored-energy mechanism than the coil, or I am about to rediscover the coin flip with extra steps.
Evaluate one explicitly in a plan and let the record judge it; do not size it.
(08-07 addendum — 3rd straight day, and the first one where the failure was mine rather than an
oversight. I *did* evaluate the down-gapper as this lesson asked: **TTD**, −28.9% gap, and declined it
on a stated mechanism — "the sell side is capitulating TO the price, not below it; a broken
multi-quarter narrative (−80.7% from highs) is the weakest possible member of the cohort". It closed
**+6.90%, the single best name in the pool**. And the cohort effect showed up again across the whole
field: gap ≤ −1% → n=6, mean +2.66%, median +2.85%, 3 of 6 cleared +2% (TTD +6.90, AVEX +5.98,
BIYA +4.14); gap ≥ +1% → n=12, mean −0.42%, 1 of 12 cleared (TEAM, my own pick, at +2.20); flat →
n=11, mean +0.70%. So on this tape the *entire* right tail sat in the down-gap cohort while the
up-gap cohort was net negative. Still not a rule and still not a gate — n is small, one flat-SPY day,
and the 08-05/08-06 caveat holds that direction inside the group is roughly a coin flip with a fat
right tail. What changes: the "how broken is the narrative" filter I used to decline TTD has no
forward support and cost me the day's best name — a deeper derating may be *more* overshoot into the
open, not less. Next time, reason about the down-gapper on the overshoot mechanism itself and let the
record judge it, rather than re-deriving a story reason to pass.)
(08-10 addendum — **first time TRADED, and it worked.** MNDY: double beat sold off on a soft Q3 guide,
premarket +6.0% → −14.1% then a flat 83-85 base for an hour on 53.85x volume; I bought the open at 81.4
*because* the overshoot low was already printed and the base said the flush was done — the mechanism
itself, not a narrative — and it closed **+9.30%, the #1 name of 35 in a pool that averaged −0.78%**.
That is 4 distinct days of forward support (08-05, 08-06, 08-07, 08-10) and the lesson's first paid
instance. But the SAME day narrows it, and this is the part that must not get lost: the down-gap
**cohort** was 2-of-3 RED (SBET −3.21, SMR −6.23, mean −0.05%, median −3.21%). So the edge is NOT
"a down-gap is a buy" — the cohort statistic does not repeat on demand. What repeated is the specific
read: a HARD *beat* repriced down on a secondary concern, flushed violently in a thin premarket, and
then **visibly stopped making lows and based** before 09:30. The base is the evidence the overshoot is
complete; without it I am just catching a bleed. Still no gate, still no gap threshold, still a coin
flip on any single name — and still do not size it.)
(08-11 addendum, one line because the record line carries the detail: the down-gap ≤−1% cohort beat
the up-gap cohort a **5th** day (+0.92% vs −0.44%, up-gap 0-for-7), and the pool's **only** >+2% name
was HIMS, a −6.90% gapper with news_n=10 — which I never even evaluated. The process failure is not
that I passed it, it is that the down-gapper never entered the reasoning at all, a regression from
08-07 and 08-10 where I at least argued it. Look at the cohort explicitly, every day, then decide.)

**L4 — The coil axes have not discriminated one winner from one loser in my TRADED record; the
catalyst has.** (forward-earned 08-06 + 08-07 + 08-10 — three distinct days, six distinct names, and
the "watch" item I have now carried for three sessions) Traded scorecard by coil status: **coiled
picks 1-1** — MGNI (atr pctile 0.037) +5.79 win, CART (atr pctile 0.09, bottom-decile on every axis)
+0.34 loss; **uncoiled catalyst-only picks 3-1** — INSM +3.11, TEAM +2.20, MNDY +9.30 wins, ACHR −2.42
loss. Nor does the fallback axis save it: `loaded_spring` was the *only* stored-energy claim on both
MNDY (−81.3% max DD) and ACHR (−67.4%), and they finished #1 and #26 of 35 on the same day — so the
spring did not separate them either. What separated them was the catalyst: an own-numbers beat
overshooting down vs. a dilutive deal on the acquirer. Conditioning (NOT a licence to delete
principle #1, which still supplies the coin-flip warning and the magnitude logic, and NOT a rule that
coil is worthless — the sample is 6): **stop using coil presence or absence as the reason to take or
pass a name.** When the coil is absent, say plainly "this is a catalyst bet" and then spend the
reasoning where the record says the discrimination actually lives — on the catalyst's *direction and
durability*, not on how quiet the chart was. And when the coil IS present with no durable catalyst,
L1 still stands: it is inert. The open question this leaves, which only the record can answer: whether
a genuine coil adds anything at all on top of a catalyst I already believe in — 6 names cannot tell me,
so keep taking clean coils when they come with a trigger and let the count grow.

**L5 — A hard catalyst that pays out YEARS from now finishes re-rating in the overnight auction; my
session gets the give-back, not the release.** (forward-earned 08-10 ACHR + 08-11 FRMI — two distinct
days, two distinct names, the same failure shape, against three contrasting winners.) The losers:
**ACHR** −2.42% (Boeing's Wisk/SkyGrid/Insitu bolted onto a pre-revenue eVTOL) and **FRMI** +0.64%
under the bar (a binding 15-year, ~$6.5B TensorWave lease whose **occupancy starts H2 2027**). Both
were pre-revenue/speculative developers, both had genuinely durable catalysts, both printed their
entire re-rate after hours (+17.7% and +35%→+21.3% gaps) and then did nothing through the session.
The winners: **INSM** +3.11 (FY guide raise), **TEAM** +2.20 (quarter beat + FY27 raise), **MNDY**
+9.30 (double beat) — all events that move numbers the sell side is modelling *this quarter*, and all
three carried a full session. **This is not L2 resurrected**: INSM gapped +26.5% and TEAM +32.3%, as
hard as either loser, and still added their +2% — gap size is not the variable. The mechanism is what
remains to be *discovered* after 09:30. An earnings print has a day-long remodelling process — revisions,
PT changes, desks re-underwriting a number that lands this quarter — so the discovery runs through my
holding window. A 2027 contract has none: everyone who will ever value it can value it in the first
five minutes of the tape, so the auction is complete before my entry and the session is give-back and
noise. Nor does this promote the HARD ≠ HARD-UP candidate below — FRMI's number pointed **up** (a
contract it receives), so it failed on a different axis: *when* it pays, not *which way*. Conditioning,
not a gate and not a number: when the catalyst is a multi-year promise (contract, partnership, deal,
distant approval) on a name with no current numbers to remodel, treat the open as **already fully
priced** and require something else to carry the session — a base that holds and *extends* off the
open, a live sector bid, a squeeze — rather than resting on how durable the contract is. Against
over-trusting this: n=2 losses, one of them still closed green and beat a red SPY by +1.17pp, and I
have no instance yet of a distant-catalyst name that *did* run, so this is a re-weighting of L4's
durability question with a second axis — **when does it pay** — not a reason to refuse the trade.

_(Candidate, NOT yet a lesson — "HARD ≠ HARD-UP": ACHR 08-10 was the hardest catalyst in the record
by durability and still fell, because I was buying the **acquirer issuing 19.75% dilution** — a HARD
number whose re-rate points down for the buyer. Every winner so far moved the company's OWN numbers up
(INSM guide raise, TEAM beat+raise, MNDY double beat). But this is **n=1**: the closest prior case,
MGM 08-05, failed on a SOFT catalyst, not a HARD-but-down one, so there is no repeat to earn a lesson
from. Logged here to be judged, not applied as a rule. If a second HARD-catalyst pick fails on the
direction of the number rather than the coin flip, promote it.)

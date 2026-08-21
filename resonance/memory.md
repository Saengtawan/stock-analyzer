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
bet direction — lean toward abstain when the only catalyst is soft **AND nothing is supplying
direction**. What can still supply direction on a soft catalyst is a **live buyer flow**: a
still-running theme pulling momentum money in day after day, or a forced short-squeeze (a mechanical
buyer obliged to buy UP). When a soft-catalyst name is ALSO releasing on a live theme + real
participation (heavy volume, a squeeze), it is not the coin-flip a lone narrative is — take it to the
"who buys at my open" test (is that flow still arriving or already extended/consumed?) rather than
skipping it reflexively as "just soft." The FORWARD RECORD judges.

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

2026-08-12 | pool 31 → pick **QNT** (single pick, 5th non-abstain) | QNT = the FIRST pick in the record pairing a bottom-percentile coil with a hard own-numbers catalyst — atr_pct_pctile **0.000**, bb_bandwidth_pctile **0.000**, bb_squeeze_106 true, consol_len 6, rvol_short_pctile 0.028, −34.8% from the 252d high with recent rets pure chop (no discharge pop) — plus Quantinuum's **FIRST print as a public company** (Q2 rev $8M vs $7.6M consensus, +279% y/y; FY26 guide $28-32M vs a $26.5M street) = a debut beat WITH a guide above consensus, the INSM/TEAM/MNDY shape; bought as an explicit **L5 carve-out** — a debut print is the maximum-remodelling event (the sell side has no model history and must build one today, so discovery runs through my holding window) — with the evidence stated up front that the auction had NOT finished overnight: after-hours only **+1.46%** and the open only **+3.34%**, versus FRMI's +35% and ACHR's +17.7% pre-priced re-rates; weak legs named in advance: no XLK bid (7th of the sector board 08-11), a thin 56k-share premarket (~$3.3M), and float/short/options all null = WHO unverifiable | fwd (SPY open→15:55 **−0.28%** — a flat/red tape; pick filled natively, no grader intervention): **QNT +20.25% (vs SPY +20.53)** — open 59.65 → 15:55 71.73, the **#1 name of 31** and the largest single-name return in the record (prior best MNDY +9.30). The path is the thesis rather than a lucky print: it **never traded below the open** and drifted up essentially all session (09:35 60.78, 10:00 63.73, 11:00 66.33, 12:00 68.06, 15:30 71.70) = the day-long remodelling the L5 carve-out claimed, not a gap-and-fade. The field was dead: pool mean **+0.32%**, median +0.04%, 16/31 green, only **2/31 >+2%**. NAMED CORRECT-SKIPS, every one with a stated mechanism and every one validated: **APLD −3.77%** (+7.98% gap whose catalyst I could not name — pool's 2nd worst), **SMR −2.59%** (spring already discharged +7.73% into the prior session), **HIMS −1.66%** (its L3 rebound was spent YESTERDAY, when it was the pool's only >+2% name — first time I applied L3 in the *negative* and it held), **KLAC −0.87%** (soft CNBC 'Final Trades' catalyst, no coil, split-artifact spring), **CZR +0.14%** (131x premarket volume on a flat price with news_n=0 = a cross, not a direction). L1's triggerless cohort inert a **6th** straight session: 19 named, MFP −4.04 to CATY +0.92, none cleared. MISSED 1 >+2%: **NINE +3.40%** (news_n=0, atr pctile 0.376 — neither coiled nor catalyst-bearing, the cheapest miss column there is). Cohorts: up-gap ≥+1% n=6 mean +1.87% (1 of 6 cleared, and it was mine); **no down-gap ≤−1% cohort existed at all** (deepest was MFP −0.60%), so the 5-day down-gap tilt got no test today | JUDGMENT: **1 win / 0 loss / 5 named correct-skip (+19 inert L1 cohort) / 1 missed.** Honest takeaway: this is the cleanest process win in the record — the only name that carried BOTH legs the system was built on, taken for reasons written down before the open and validated by the *path*, not just the close. Three disciplines against over-reading it: (a) I cannot separate the coil's contribution from the catalyst's — CART was a genuine bottom-decile coil and lost — so n=1 does **not** answer L4's open question; it only stops the coil case from getting weaker. (b) +20% is a tail, not the EV of this setup, and the reason that tail existed is that nobody had a model yet — a rare condition, not a repeatable screen. (c) The weak legs I flagged (no sector fit, thin premarket, WHO unverifiable) were all real and all irrelevant today; that is a reminder they are not veto-grade, not proof they never matter. What generalizes is the test I ran: I did not reject a hard catalyst for gapping, I asked what was left to discover after 09:30, and for once the answer was "almost everything."

2026-08-13 | pool 35 → picks **GO + EQPT** (6th non-abstain) | EQPT = the QNT shape repeated — bottom-percentile coil (atr_pct_pctile **0.000**, bb 0.361, rvol_short 0.172, −41.8% from the 252d high) paired with a HARD own-numbers surprise (Q2 adj EPS $0.18 vs $(0.07) est = expected loss → real profit, sales $1.449B vs $1.152B) on a thinly-covered recent listing whose overnight auction visibly had NOT finished (gap only **+7.4%**); GO = an explicit CATALYST-ONLY bet with the coil leg stated ABSENT up front per L4 (atr pctile 0.136, bb 0.392, consol 0; loaded_spring only, −47.1% from highs) — Q2 beat $0.20 vs $0.12 **with a multi-line FY26 guidance RAISE** (comps −2.0%-to-flat → −0.5%-to-flat, revenue midpoint above consensus, EBITDA and EPS floors lifted) = the INSM/TEAM/MNDY/QNT current-numbers-remodel shape, taken on the L5 axis with AH +12.2% already given back to a +9.64% premarket mark | fwd (SPY open→15:55 **+0.38%**; both picks filled natively, no grader intervention): **EQPT +4.64% (vs SPY +4.26), GO −3.23% (vs SPY −3.61)** — EQPT #5 of 35, GO **#30 of 35**; field mean +0.92%, median +0.09%, 20/35 green, 7/35 >+2%. NAMED CORRECT-SKIPS: **GLNG −7.27%** (pool's worst — passed on L5, a $2.45B EPC deal for a vessel delivering years out *plus* $2.45B of capex going out; my stated falsifiable "if GLNG closes >+2% then L5 is over-applied" SURVIVED), **YETI −1.15%** (the base test held here — still printing its session low on the final premarket bar), **HIMS −3.30%** (L3 rebound already spent 08-11, 2nd straight day applying L3 in the negative and it held), KLAC +0.61, CVBF −0.37, WKHS +1.31. MISSED 6 >+2%: **LUNR +22.80% (#1 of 35)**, **OPEN +12.62%**, **STUB +8.65%**, QURE +4.74, SMR +3.85, MSTR +2.39. Cohorts, and they are stark: down-gap ≤−1% **n=4, mean +10.73%, 3 of 4 cleared**; up-gap ≥+1% **n=5, mean −0.76%, 1 of 5 cleared (EQPT, mine)**. L1's triggerless cohort **broke its 7-session inert streak in BOTH directions** — QURE +4.74 and SMR +3.85 cleared while SOC −5.96, ERAS −5.80, NINE −4.71 blew out; they released, direction random (principle #1 intact, L1 must not be hardened) | JUDGMENT: **1 win / 1 loss / 6 named correct-skip / 6 missed.** Honest takeaway, and it is not about my picks: **all three of my big misses printed their session low AT or BEFORE 09:30 and never traded below the open again** — STUB low 7.15 at the open then straight to +8.65; LUNR opened 14.30, first bar 15.73, closed 17.56; OPEN low at 09:35 then one-way to +12.62. I declined STUB in writing this morning *because* it was "a five-hour grind of progressively lower lows... no completed overshoot, so no base to buy", and stated that as falsifiable. **It failed.** The bleed ended at 09:30 — which is the entire point of the mechanism and the opposite of what my filter assumed. LUNR I declined as "a straight double miss is just a miss" per L3's own 08-10 narrowing; it was the best name of the day. OPEN I declined on the HARD≠HARD-UP candidate (0% converts get delta-hedged short = supply); the dilution repriced overnight to a −7.87% gap and my session got the rebound — so that candidate does **not** get promoted, it just took its first hit. → **L6.** On my own two: EQPT is a genuine process win and the 2nd straight coil+catalyst pairing to pay (though honestly it spent most of the session *underwater*, low −4.5% at 12:35, and made all of it after 14:00 — a hold-to-EOD win a stop would have killed, not QNT's clean never-below-open drift). **GO is a clean loss and the first failure of the own-numbers-beat-and-raise shape that was 4-0** (INSM/TEAM/MNDY/QNT) — it opened 11.14, fell to 10.28 within five minutes, and its high of day never got back to my entry. n=1 does not overturn that shape, but two things I do not get to wave away: the raise was a *less-bad* re-rate (comps still negative) and the whole +9.64% mark rested on ~$600k of premarket — and I wrote **both** of those in my own risk note and bought anyway. That is now three times (ACHR, FRMI, GO) I have named the exact failure mode pre-open and taken the trade regardless.

2026-08-14 | pool 33 → pick **GLOB** (single pick, 7th non-abstain) | GLOB = the first name taken *purely* on L6 — a violently flushed down-gapper with the coil leg stated ABSENT up front per L4 (atr_pct_pctile 0.494, bb **0.844**, consol 0; loaded_spring only, −48.5% from the 252d high), so the "stored energy" claimed was the overnight dislocation itself: prev_close 41.02 → premarket low 34.34 (−16.3%), gap −12.24% on **19.87x** premarket volume, pm_last 36.00 in the upper third of the pm range. The catalyst read: FY26 revenue guidance trimmed ~**1.5%** at the midpoint (2.462-2.508B → 2.428-2.462B) and the market took ~14% off the stock for it, 8 negative headlines and "Analysts Cut Their Forecasts" still printing at 08:40 ET = a narrative reprice (AI eating IT services) far larger than the number that changed, the L6 thin-book overshoot; taken with the explicit statement that my four prior reasons for declining this setup are 0-for-4 forward (TTD/HIMS/STUB/LUNR) and I had no NEW one | fwd (SPY open→15:55 **−0.29%** — a flat/red tape; pick filled natively, no grader intervention): **GLOB −2.19% (vs SPY −1.90%)** — open 38.21 → 15:55 37.38, **#31 of 33**, and the path matters: it did NOT reject instantly — it rallied to 38.75 (+1.4%) inside the first hour, then rolled over for five straight hours to 36.33 (−4.9%) at 13:00 and only limped back to −2.19%. The field was dead: pool mean **+0.10%**, median +0.02%, 17/33 green, only **3/33 >+2%**. NAMED CORRECT-SKIPS, 8 with a stated mechanism: **SMR −4.09%** (pool's worst — spring discharged, +7.73/−6.52/−3.03/+2.71/+3.85 into the day, soft catalyst), **AMPX −3.14%** (2nd worst — the +8.92% up-gapper whose catalyst I could not name; **my falsifiable "if AMPX closes >+2% the unnameable-gap skip is costing me" SURVIVED**, and it repeated APLD 08-12 exactly), **MSTR −2.01%** (news-extreme but the trigger pointed down — MSCI exclusion + BTC sliding), **KLAC −1.62 / BKNG −0.36** (split-artifact springs, 3rd time flagged), **SOC −0.24** (no event = falling knife, not an L6 overshoot), **TECH +0.25** (the best coil in the pool — atr 0.000, bb 0.004, consol 34 — with its trigger pointing sideways-down: a Wells Fargo downgrade to a $73 PT against a 72.17 close; it did nothing, exactly as argued), **ROKU +1.43** (merger-arb pinned to Fox's $160, 3rd straight correct call on the same mechanism). L1's triggerless cohort inert a **9th** time in ten sessions — 19 named, PURR −1.40 to AUB +0.88, the six coiled regional banks moved together (+0.40 to +0.88) and none cleared. **NAMED SKIP THAT WAS WRONG: WKHS +2.81%** — I declined it on the SIZE of the reprice ("only −4.47% on 1.67x pm volume, nothing overshot"), and it was one of the day's three winners. MISSED 3 >+2%: **NINE +5.45** (news_n=0, loaded_spring only — its 5th appearance in a miss column, but it printed −4.71% yesterday, so it is a two-tailed $-name with no pre-open tell, the cheapest miss there is), **QURE +3.05** (news_n=0 triggerless coil, its 3rd >+2% day of the record after 08-06 +2.85 and 08-13 +4.74), WKHS +2.81. Cohorts: down-gap ≤−1% **n=3, mean −0.46%** — and it inverts within itself, the DEEPEST gap (GLOB −12.24%) was the loser and the SHALLOWEST (WKHS −4.47%) the winner, so the 08-13 down-gap tilt did not repeat; up-gap ≥+1% n=2, mean −1.53%, 0 of 2 cleared | JUDGMENT: **0 win / 1 loss / 8 named correct-skip (+19 inert L1 cohort) / 1 named skip wrong (WKHS) / 3 missed.** Honest takeaway: **my own falsifiable call FIRED against me.** I wrote pre-open that if GLOB closed below −2% then L6 is being over-applied to *guidance-cut* down-gappers as against *headline-shock* ones, and it closed −2.185%. But the discriminator I actually earned today is not "guidance cut" — it is in risk note (2), which I wrote and then overrode: *"the downgrade flow is still landing INTO my open and will keep printing through the session… if that reasoning is wrong, this is where it breaks."* The path says it broke exactly there: the L6 rebound started (+1.4% in hour one) and was then sold for five hours by the estimate cuts I had already identified as still arriving. Every L6 winner was a **completed** repricing — a one-off shock (STUB, LUNR, OPEN's convert, MNDY's soft guide on a double *beat*) whose bad news was fully in the overnight auction; a guidance cut is not one event, it is the start of a revision cycle that runs through my session. That is the discriminator inside the cohort my falsifiable call asked for, and L6's core stays intact: the flush does not have to end before 09:30 — but the *news* does. Second, and this is the fourth day of it: ACHR, FRMI, GO, now GLOB — I named the exact failure mechanism in my own risk note and bought anyway, four for four. → **L7.** Two things I do not get to claim: WKHS proves nothing on n=1 (I rejected it on reprice size and was wrong, but that same test is what correctly rejected SOC today), and the abstain was NOT the free alternative — 30 of 33 names failed to clear +2%, so the pool, not the pick, was the problem.

2026-08-17 | pool 37 → pick **LUNR** (single pick, 8th non-abstain) | LUNR = a deliberate override of my own discharge check, stated as such: coil leg ABSENT up front per L4 (atr_pct_pctile 0.344, bb 0.698, consol 0; loaded_spring only, −59.4% from the 252d high) AND already run +27% over four straight sessions (+8.20/+3.42/+3.00/+4.40, including the +22.80% on 08-13 that sits in my own miss column) — bought anyway on the single ground that the driver was an **independent NEW event dated 08:02 ET**, not a continuation: authorization to proceed on a multi-satellite comms program, anticipated value >$600M, backlog to ~$1.8B against a $3.05B market cap (~59% of cap). The override argument was L5's 08-12 unspent-auction test, made **by cohort analogy**: "FRMI printed +35% after hours and handed me a +21.3% gap; ACHR printed +17.7%. LUNR is at +3.8%" — with the premarket path as corroboration (flat 04:00-07:30, then 18.92→20.229 on 622k shares in thirty minutes vs ~180k for the prior five hours, settling 19.66-19.89 above the pre-news 18.87-19.10 base). Weak legs named: no XLI rotation (FIT), and risk note (2) said in writing *"L5's loss column is exactly this profile — a big contract on a loss-making space developer whose money arrives over years; that profile is 0-for-2 (ACHR, FRMI) and I am arguing past it with the unspent-auction test"* | fwd (SPY open→15:55 **−0.45%** — a red tape; pick filled natively, no grader intervention): **LUNR +0.64% (vs SPY +1.09)** — open 20.25 → 15:55 20.38, **#8 of 35** gradeable. Green, beat a red tape, **under the +2% bar = a LOSS** — and it is the same number and the same shape as FRMI 08-11 (+0.64%, green, beat a red SPY, under bar). The path is the honest part: underwater the first two hours (low **19.49** at 09:30, −3.75%), then the remodel I predicted actually arrived — 12:00 +1.93%, **13:00 +2.40%, through the bar** — and was then given back all afternoon (15:00 −0.15%, 15:30 −0.44%) to close +0.64%. User's dynamic limit: winLo (09:05-09:25) **19.7649** → limit **20.06**, filled on the first bar (RTH low 19.49) for **+1.60%** — better than the +0.64% open entry, still under the bar. Field was dead: pool mean **+0.16%**, median +0.03%, 18/35 green, only **4/35 >+2%**. NAMED CORRECT-SKIPS, 9 with a stated mechanism: **SOC −3.73%** (pool's worst — triggerless deep drawdown), **BKNG −2.92 / KLAC −0.58** (split-adjustment artifact springs, 4th flagging), **LEU −2.72** (26.68% short float but news_n=0), **PURR −1.52%** (best coil in the pool, atr/bb/rvol all bottom-1% and NOT discharged, rejected as HYPE-token mNAV beta = a mechanism trading through my session in both directions; **my falsifiable "if PURR closes >+2% then a token-beta gap on a genuine coil is tradeable" SURVIVED**), **QURE −0.19** (discharged + soft), **ARX −0.13** (called as a DATA ARTIFACT — last_close six sessions stale, the +57.74% "gap" not real; confirmed, it opened 19.57 and did nothing), **VIST +1.09** (monotonic premarket fade into my open on a broken pm_vol denominator), **NTSK +1.87** — and I flag that one honestly: my falsifiable was ">+2%" and it closed **+1.87%**, so the reprice-SIZE filter survived by 13bp, which is a near-miss, not a validation. L1's triggerless cohort inert a **10th** time in eleven sessions — 22 of 24 gradeable, ACA −0.23 to CBZ +0.33, only DYN +2.55 and CNQ +2.00 cleared. **NAMED SKIPS THAT WERE WRONG, 3:** **WKHS +8.12% (#1 of 35)** and **NINE +2.45%** — both dismissed in one line as "triggerless deep-drawdown names, i.e. falling knives, not loaded springs" (SOC, the third name in that same line, was correct at −3.73); and **SBET +4.16%** (ETH-treasury proxy passed on net sentiment −2). MISSED 4 >+2%: WKHS +8.12, SBET +4.16, DYN +2.55, NINE +2.45 (CNQ +2.00 exactly at the bar) — every one of them news_n=0 or news-negative with no gap, i.e. the entire right tail sat outside what a catalyst-led process can surface. Cohorts: up-gap ≥+1% **n=4, mean +0.02%, 0 of 4 cleared** (VIST, LUNR, ARX, PURR); down-gap ≤−1% n=1 (NTSK +1.87), so no test of the down-gap tilt today | JUDGMENT: **0 win / 1 loss / 9 named correct-skip (+22 inert L1 cohort) / 3 named skips wrong / 4 missed.** Honest takeaway: **I quoted L7's tell verbatim and then did the thing anyway.** My risk note said I was arguing past L5's 0-for-2 loss column *with the unspent-auction test*, and L7 says in as many words that when I catch myself countering a this-name risk with a cohort analogy, the name wins that argument — I even supplied the cohort (FRMI/ACHR gap sizes). It is now **0-for-5** (ACHR, FRMI, GO, GLOB, LUNR) and L5's distant-payout loss column is **0-for-3**. What I did learn that is new: the unspent-auction test **half-worked** — the release came and cleared +2.40% at 13:00, so a small gap on a big award is not simply "already priced" the way FRMI was; it did not *hold*. A multi-year award recruits momentum money that takes the afternoon off; an earnings print recruits desks that must finish a model, which is why INSM/TEAM/MNDY/QNT/EQPT carried to the close. Unspent is necessary, not sufficient — what has to be unspent is a **current-numbers remodel**, not attention. Two things I do not get to claim: my stated falsifiable did NOT fire (I wrote "if LUNR closes **red**" and it closed green) — but that is a mis-specified test, not a survival, because my bet is the +2% bar and I set the falsifiable somewhere my own thesis could not be hurt; and the abstain was not obviously free — 31 of 35 names failed the bar, and the four that cleared were names no reasoning of mine surfaces.
2026-08-18 | pool 38 → pick **KLAR** (single pick, 9th non-abstain) | KLAR = the first pick in the record where BOTH legs were genuinely present — atr_pct_pctile **0.059** (bottom 6% of its own year, unlike the catalyst-only buys GLOB 0.494 / MNDY 0.513 / TEAM 0.53 per L4), −65.8% from the 252d high, recent rets pure chop — paired with a HARD own-numbers current-quarter print: Q2 double beat (adj EPS $0.01 vs −$0.05, sales $1.042B vs $993.4M, GMV +18%, transaction-margin dollars +42%) sold **−20.15%** on a FY26 revenue guide cut ($4.08-4.16B vs $4.415B street) on **94.06x** premarket volume / pm_range 23.95%. The thesis was the *composition* of that cut: ~$600M attributed to CURRENCY TRANSLATION plus a conservative German-volume assumption, while the same release RAISED the FY transaction-margin-dollar guide ($1.62-1.65B) and held adj operating income — i.e. the profit line was held-to-raised, so the overshoot should be re-read by desks INSIDE my session (the MNDY shape). FIT stated ABSENT up front (no XLF bid on a −0.47% SPY board) per L7's survivable class. Risk note (1) named the adverse mechanism explicitly and in L7's own vocabulary: *"PT cuts on a 7% lower revenue base will print through today's session… that flow is real and adverse and it is present, not absent — L7's 0-for-5 category"*, then applied L7's discipline step and offered two THIS-NAME observables as the exception (KLAR raised margin dollars where GLOB's cut was pure; KLAR atr pctile 0.059 where GLOB was 0.494) | fwd (SPY open→15:55 **−0.17%** — a flat tape; pick filled natively, no grader intervention): **KLAR −3.83% (vs SPY −3.66%)** — open 15.66 → 15:55 15.06, **#35 of 38**, and the path is the whole story: it popped to **16.18** in the first five minutes (+3.3%), never traded there again, and ground down all session to a 15.25 low at 11:55. **My pre-registered falsifiable FIRED** ("if KLAR closes below the open, the FX-driven-revenue-cut-with-offsetting-margin-raise mechanism is wrong"). Entry-limit comparison, graded at the CLOSE per the 08-18 method lesson (never grade a resting limit intraday): winLo(09:05-25) **15.32** → flat ×1.015 = **15.55 filled 09:50 → −3.15%**; AI-judged ×1.008 = **15.44 filled 09:55 → −2.46%**; market-at-open −3.83% — **both limits beat the open, tighter priced better, all three still losses** (n=1, and the tighter limit won only because the tape kept falling). Field was dead: pool mean **−0.70%**, median −0.22%, 10/38 green, **1/38 >+2%**. NAMED CORRECT-SKIPS with a stated mechanism: **BIDU −3.99%** — passed on the dual-listing argument (traded a full 9888.HK session on the print, so the −8.59% was not a thin US premarket book and no overshoot was left for my open to unwind), and **my falsifiable "if BIDU closes >+2% the dual-listing argument is wrong" SURVIVED**, decisively; **KLAC −0.25 / BKNG +1.22 / CVNA −3.85** (split-adjustment artifact springs, 5th flagging, none cleared). L1's triggerless news_n=0 cohort inert an **11th** time in twelve sessions — 32 names, mean **−0.64%**, **0 cleared +2%**, WKHS −5.76 to BKNG +1.22; note WKHS (−5.76) and NINE (−2.12) were both in yesterday's *skips-that-were-wrong* column and were correct skips today, which is what a two-tailed no-tell name looks like. MISSED 1 >+2%: **RDW +2.70%** — and this is the honest one, because unlike 08-17's right tail it sat INSIDE what a catalyst-led process can surface: a real coil (atr_pct_pctile 0.064, consolidation axis) on a −4.85% down-gap with news_n=1 and net sentiment **+1**, i.e. the same down-gap-with-a-nameable-event shape I bought, but with the news pointing UP instead of a guide cut. Cohorts: down-gap ≤−1% **n=7, mean −0.90%** — and it splits by news direction, the only clearer (RDW, sentiment +1) was the one whose print did not cut a number, while both cut-guidance names (KLAR −3.83, BIDU −3.99) were the two worst; up-gap ≥+1% **n=0**, no test | JUDGMENT: **0 win / 1 loss / 4 named correct-skip (+32 inert L1 cohort) / 0 named skips wrong / 1 missed.** Honest takeaway: **on the same day, the same question answered in two directions — and only the passing direction paid.** For BIDU I asked "what is left to discover after 09:30?", answered "nothing, the reprice completed in a full HK session", and passed correctly; for KLAR I asked the identical question, answered "a remodel is left", and lost 3.83%. The record now says the *nothing-is-left* form of that argument is the reliable one and the *a-favourable-remodel-is-left* form is not, when the news is a **guidance cut**: GLOB 08-14 and KLAR 08-18 are the same trade — a guidance-cut down-gapper bought on a composition/overshoot argument, both with a pre-registered falsifiable, **both fired** → **L8**. Second, L7 is now **0-for-6**, and this instance is worse than LUNR's: I did not merely quote the tell, I *executed L7's own escape hatch* — named two observable this-name differences from the covering loss column rather than a class analogy — and it did not save the trade, so the escape hatch is not the safety it reads as → **L7 addendum**. Two things I do not get to claim: the abstain was not free but it was close — 37 of 38 names failed the bar, so a pass costs almost nothing on a field like this one, which is a *fact about the field*, not a licence for blanket timidity; and the coil leg is not what failed — atr pctile 0.059 was the best coil I have bought and the loss came entirely from the catalyst's direction, so L4's "say when the coil is absent" discipline is untouched and the KLAR result must NOT be read as evidence against buying real coils.

2026-08-19 | pool 36 → pick **DUOL** (single pick, 10th non-abstain) | DUOL = a CATALYST-only bet with the coil leg stated ABSENT up front per L4 (atr_pct_pctile 0.512, bb 0.413, consol 0, rvol_short 0.938; loaded_spring only, −62.1% from the 252d high), bought on a 06:17 ET 8-K carrying PRELIMINARY INTERNAL DAU data — gap +5.86% on 12.77x premarket volume, pm_range 9.92%, into a 20.72% short float on a 39.95M float. The load-bearing sentence was *"a company 62% off its highs does not volunteer mid-quarter data to confirm the bear case"*, i.e. an argument from INTENT, plus an L5 unspent-check ("+5.86% of re-rate against a name down 62% — a great deal left to discover after 09:30") and an explicit L7/L8 check that the post-open flow pointed UP, not down (no number was being cut — the inverse of GLOB/KLAR) | fwd (SPY open→15:55 **−0.17%**): **DUOL −2.06% (vs SPY −1.89%)**, open 148.97 → 15:55 145.91, **#29 of 36**; path = flush to 142.16 by 09:50, pop to 150.23 at 10:35 (**+0.84% over the open, never within reach of +2%**), then five hours of bleed. **My pre-registered falsifiable FIRED** ("if DUOL closes below the open, then a mid-quarter preliminary-data 8-K with no guidance change is NOT a current-numbers remodel my session gets paid for"). **WEB-CONFIRMED FACT that indicts the thesis at its premise, and it was readable pre-open in the filing itself:** the 8-K was not a company *volunteering* anything — it was a **Reg FD cure for an INADVERTENT disclosure**: on 08-18, during an in-person investor meeting at the company's offices, *a screen in the meeting room inadvertently displayed* an estimated 08-17 DAU growth rate of **+27.4% y/y**, so the company was OBLIGED to file. Nothing was signalled. I quoted the release's disclaimer boilerplate and did not read its substance. Note the sharp half: the datapoint itself was **good** (+27.4% vs the +23% DAU growth reported for Q2) and the stock still faded — a favourable number with no formal guidance change gave desks nothing they were obliged to publish against, which is exactly what my own risk note (1) said ("it sits between HARD and SOFT… a story with no fresh number the market must re-rate to often sells off intraday — that ambiguity is the real weak leg") and which I then overrode → **L7 now 0-for-7** | **FIELD WAS ALIVE, unlike 08-18: pool mean +0.80%, median −0.00%, 17/36 green, 8/36 cleared +2%** — and I named three of the winners in my own skip column | **NAMED SKIPS THAT WERE WRONG (4):** **BNTX +3.41% (vs SPY +3.58)** — the unnameable-gap skip, 3rd application, and **its falsifiable FIRED**; web now names the catalyst plainly: the Pfizer/BioNTech **XFG-variant-adapted COVID vaccine won EU/EEA authorization for 2026-27**, alongside an oncology-pipeline re-rate — so "I could not source it" was my TOOLING failing on a public regulatory approval, exactly the honest counter I wrote into the skip; the filter is now **2-for-3** (APLD −3.77, AMPX −3.14, BNTX +3.41), and note it gapped **+15.74% and still added +3.41% from the open** = L2 again, a gap does not consume the remaining range. **CCOI +8.03% (vs SPY +8.20), #2 of the pool** — skipped as "L7's 0-for-6 category, cleanly: fresh downgrade flow present and operating THROUGH my session" (JPM to Underweight, PT **$22 → $9**, gap −5.73%). Fact: the session **low was 9.03** — the stock traded straight to the new target inside the first 20 minutes and then reversed all day to close **at the session high**. A single desk's downgrade is a **one-shot** reprice that can complete at the open; it is not the multi-desk revision cycle L8 describes after a company cuts its OWN forward number. I applied L7/L8 to a *skip* for the first time and it cost me the pool's #2 name (n=1 — prior downgrade-skip TECH 08-14 +0.25 was correct, so this is 1-1, NOT a lesson). **WKHS +2.78%** — declined with the (correct, L1-compliant) "no trigger, so no directional edge"; it is now **0-for-3 against me** (+2.81 08-14, +8.12 08-17, +2.78 today) with one correct skip (−5.76 08-18) — still a two-tailed no-tell name, but the tally is one-sided enough to log. **BKNG +2.32 / CVNA +6.99** — split-adjustment-artifact springs, 6th flagging, and the **first time the flagging has cost**: KLAC −4.54 correct, but two of three cleared +2%. **NAMED CORRECT SKIP:** KLAC −4.54. **L1's triggerless news_n=0 cohort BROKE its inert streak (was 11-of-12 sessions):** 29 names, mean **+0.41%**, median −0.09%, 12 green, and **3 cleared +2% — SOC +17.49 (#1 of the pool), FMC +5.00, NINE +4.69**. Hindsight guard on SOC, which is the whole reason this is not a self-flagellation: it traded **4.02–4.14 flat from 09:30 through 13:00** and only went vertical after ~13:45 — an INTRADAY event, unreachable by any pre-open process, and I could not source it post-close either. The regional-bank sub-cluster stayed reliably inert-to-negative (MTB/AUB/BOKF/EBC/FULT/TCBI/WSFS/ALLY mean **−2.49%**, 0 cleared). Cohorts: **up-gap ≥+1% n=9, mean +3.48%** — and DUOL, the name I bought, ranked **8th of 9**, while the four best (SOC/CVNA/FMC/BNTX, +17.49/+6.99/+5.00/+3.41) were news_n=0 or news-light; **down-gap ≤−1% n=1** (CCOI +8.03) | JUDGMENT: **0 win / 1 loss / 1 named correct-skip (+ the 8-name bank cluster inert) / 4 named skips wrong / 3 missed >+2% (SOC intraday-driven, FMC, NINE).** Honest takeaway: **my last three picks — LUNR, KLAR, DUOL — are the same trade wearing different catalysts, and the clause they all rest on is MINE, not the company's.** Each one bought "a remodel is still left for my session," supplied by my own interpretation (backlog re-rate / composition of an FX-driven cut / what preliminary DAU data implies), and each failed: +0.64% under the bar, −3.83%, −2.06%. DUOL is the case that breaks L8's frame — **nothing was cut, the news pointed UP, the datapoint was good, and it still faded** — so the failing ingredient is not "a guidance cut," it is the *interpretive step* itself → **L9**. The second thing I do not get to dodge: the field cleared +2% eight times and my process put me in the one up-gapper that fell, so today is not "a hard tape," it is a selection loss.

2026-08-20 | pool 41 → pick **BULL** (single pick, 11th non-abstain) | BULL = a CATALYST-only bet with the coil leg stated ABSENT up front per L4 (atr_pct_pctile read 0.012 but I refused it as a lagging print against recent_max_abs_move_5d 8.816; loaded_spring only, −71.1% max drawdown, −46.1% from the 252d high, $4.28B cap at $8.64), bought on the class L5 calls the WIN class and my traded record had never lost with: a HARD, company-printed, current-quarter double beat — Webull Q2 AMC 08-19, revenue $198.8M vs $187.3M est (+51% y/y), adj EPS $0.07 vs $0.03, record adj operating profit +169% to $62.6M, customer assets +79% to $28.5B — with a STRUCTURAL driver (the SEC's elimination of the pattern-day-trader rule is a run-rate change to volumes, not a one-quarter print), 31.09x premarket volume, pm_range 8.45%, 6.05% short float with short interest GROWING into the beat, put/call 0.191, zero analyst revisions printed yet. L9 passed cleanly and honestly — the load-bearing clause was the COMPANY's number, not my interpretation, which is exactly what GLOB/LUNR/KLAR/DUOL lacked. The leg I got wrong was L5's unspent check, and I got its SIGN backwards: BULL printed +14.7% after hours to $9.91 and opened at 9.94 (gap **+15.05%** off an 8.64 close), and I wrote that HOLDING ~90% of the re-rate into my open was evidence the auction was unspent. L5's plain reading says the opposite — a large AH re-rate that is still intact at 09:30 is a **completed** reprice, and holding it means the marginal buyer finished before my entry, not that one is still coming. | fwd: **BULL −11.12%** (open 9.94 → 15:55 close 8.835; vs SPY −0.43%, **vs_spy −10.68**) — the worst loss in the traded record by ~3x (prior worst KLAR −3.83%), #42 of 42 names in the pool. Path: high 9.94 in the first minute, 9.84 at 09:45 and never above the open again, one-way distribution to the bell; the ENTIRE +15% gap was given back (close 8.835 = only +2.3% over the 8.64 prior close). Pre-registered falsifiable FIRED ("if BULL closes below the open, profit-taking beats revision flow"). **WEB FACTS, and they refute the mechanism rather than the forecast: everything my thesis predicted would happen DID happen.** Rosenblatt raised its PT to $15 (22x 2027 adj EBITDA) on the results and Northland's Grondahl reiterated Buy and raised $14→$15 — the upward revision flow I said would print inside my session printed, pointing UP, exactly as written — and on the same day Webull shipped native AI connectors to ChatGPT/Claude/Grok plus a CLI and MCP tools, i.e. MORE good news landed intraday. The price went straight down for six hours anyway. So the error is not that I mis-forecast the flow; it is that upward revision flow does not carry a name whose re-rate the pre-open auction has already completed. Entry: winLo(09:05-09:25) = 9.75, flat ×1.015 = **9.896**, filled (first 5-min bar low 9.65) → −10.72% vs the open-entry −11.12%, so the limit saved 0.40pp and lost anyway; no AI-judged buffer was logged for the day, so the dual-limit comparison has no entry today. | SKIPS, and the skip discipline was the whole of today's edge: **RARE −10.97%** — the closest miss, passed on L5's distant-payout column, and its falsifiable ("if RARE closes >+2% then L5+L9 are over-applied to an FDA approval") SURVIVED decisively; web confirms the pre-open read was right for the stated reason — GENGLYCOS is an ACCELERATED approval (confirmatory-trial obligation) priced at $2.7M for a 1,500-2,500 patient US population, i.e. a multi-year launch ramp with no current number for any desk to remodel today. CRWD −3.54 (no fresh own-numbers print, L9), LEU −2.58 (analyst-note-alone = SOFT), ERAS −2.93 (triggerless wake), BILI +0.27 (search-exhaustion skip, went nowhere), crypto-beta cohort 3-of-4 right (COIN −0.25, SBET +0.80, BTDR +1.86) — the L1 triggerless cohort was inert for the 12th time in 14 sessions (16 names, best QURE +1.88, worst NAVN −1.35, not one at +2%). MISSED: MARA +9.11 (the BTC-beta coin flip landed up on exactly one of the four names I grouped it with — noise, not a selection error), FRMI +3.82 (the name I cited in my own thesis as the give-back failure shape — it ran on the day I invoked it as a cautionary tale), CVNA +2.73 (the split-artifact flag costs me for the SECOND consecutive session after BKNG +2.32/CVNA +6.99 on 08-19; BKNG −1.00 today). The field was nearly dead — only **3 of 42** names cleared +2% — so this was not a day I was unlucky to miss; it was a day my one action was the single worst name in it. | JUDGMENT: **0 win / 1 loss / 8 correct skips / 3 missed.** The honest takeaway, and it costs me the story I have been telling since 08-12: the current-numbers-print WIN class (INSM/TEAM/MNDY/QNT/EQPT/MGNI) just took its first loss and took it at −11%, so "a company-printed number" is necessary and NOT sufficient. What separates BULL from INSM (+26.5% gap) and TEAM (+32.3% gap), which both gapped bigger and still paid, is not gap size — it is that BULL had already been bid UP INTO the print (+8.82% on 08-19, ~+22% over two sessions), so my open bought the second leg of a run rather than the release of anything. I named that supply in risk note (1), called it the one session-mechanism risk I was overriding, wrote that L7's override column was 0-for-7, and overrode it — 0-for-8. The new and genuinely uncomfortable fact is that this time my counter-argument came TRUE and the trade still lost by 11%.


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
(08-13 + 08-14 + 08-17 addendum — the abstain is still right; the WORD I have been using to justify
it is not. Three distinct days I dismissed triggerless deep-drawdown names as **"falling knives"**,
and that phrase asserts a *direction* on exactly the class principle #1 says has none. Forward:
08-13 the cohort broke its inert streak **in both directions** (QURE +4.74, SMR +3.85 cleared while
SOC −5.96, ERAS −5.80, NINE −4.71 blew out); 08-14 **WKHS +2.81%** was one of three winners after I
declined it; 08-17 the same one-line dismissal covered SOC/NINE/WKHS and went **1-for-3 — SOC −3.73
correct, but NINE +2.45 and WKHS +8.12, the #1 name of the pool**. Across the record WKHS is now
0-for-2 against me and NINE has appeared in five miss columns while also printing −5.31 and −4.71 —
which is not a missed edge, it is a two-tailed name with no pre-open tell, i.e. the coin flip.
Conditioning, and it changes the *reason* rather than the decision (the same correction L2 made):
keep abstaining on a triggerless name, but say **"no trigger, so I have no directional edge"** —
never "falling knife", which is a bear call I have no basis for and which the record has now paid
against three times. Scope note: "triggerless" means genuinely NO flow — news_n=0, thin premarket,
inert tape. A name that is releasing on **heavy volume with a live theme or a forced squeeze is NOT
triggerless** and does not fall under this lesson's "no directional edge"; that flow IS a trigger,
so judge it on the Step-4 who-buys test, not by filing it with the inert cohort. The practical cost of the sloppy word is that it makes a miss feel like a good
skip: today the entire right tail (WKHS +8.12, SBET +4.16, DYN +2.55, NINE +2.45) was news_n=0 or
news-negative, and calling them knives let me file four winners as validated discipline. Limit, so
this is not over-read: the same dismissal was CORRECT on SOC twice (−0.24 on 08-14, −3.73 on 08-17)
and the cohort was inert for the 10th time in eleven sessions — the abstain is not what failed, only
the story I told about it.)


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

(08-12 addendum — the first WIN-side instance on the same axis, so read L5 two-way instead of as a
veto list. **QNT +20.25%** was a HARD own-numbers print whose overnight auction was visibly
*unfinished*: after-hours only +1.46%, open only +3.34% against a debut beat-and-raise — and it
drifted up all session without once trading below my open. The discriminator was not gap size (L2
still stands: INSM +26.5%, TEAM +32.3% both cleared) and not durability (ACHR's and FRMI's catalysts
were the more durable ones). It was **how much of the re-rate the pre-open auction had already
consumed**, which is observable before I buy — the after-hours print and the gap, read against the
size of the news. A **debut** report is the extreme unspent case: no model history exists, so the
sell side has to build one inside my session. Conditioning, still no gate and no number: ask "what
is left to discover after 09:30", treat a large AH re-rate on a distant-payout name as spent and a
small AH re-rate on a fresh current-numbers print as unspent — and hold both readings loosely, since
this is n=3 with the one win a +20% outlier that cannot be treated as the expected size of the tell.)

(08-17 addendum — the distant-payout loss column goes **0-for-3**, and it took down the 08-12 test
that was supposed to rescue it. **LUNR +0.64%**, green, beat a red SPY, under the bar — the same
number and the same shape as FRMI. The profile is now unmistakable: ACHR (Boeing deal, pre-revenue
eVTOL), FRMI (15-year lease, occupancy H2-2027), LUNR (>$600M multi-satellite award, loss-making
space developer, EPS missed four sessions earlier) — three names, three days, all a big contract on
a company with no current numbers anyone can remodel. I bought LUNR by applying the unspent-auction
test *against* this column: after-hours had barely moved it, the gap was only +3.8% versus FRMI's
+21.3% and ACHR's +17.7%, so on the 08-12 reading the auction had NOT finished. **That reading was
right about the release and wrong about the hold** — LUNR did not sit dead like FRMI, it ran to
**+2.40% at 13:00, through the bar**, and then gave the whole afternoon back to close +0.64%. So the
refinement, and it is the first thing the win/loss columns actually separate on: *unspent* is
necessary but not sufficient, and **what has to be unspent is a current-numbers remodel, not
attention**. An earnings print puts desks under an obligation to finish a model inside my session —
that flow keeps buying into the close (INSM, TEAM, MNDY, QNT, EQPT all carried). A multi-year award
has no model to rebuild; the only thing left after the headline is momentum money, and momentum
money takes the afternoon off. Conditioning, still not a gate and not a number: when the catalyst is
a distant-payout contract, a *small* gap no longer counts as evidence the session will pay me — ask
who is obliged to keep buying at 14:00, and if the answer is nobody, the midday high is the trade
and hold-to-EOD gives it back. Against over-trusting this: n=3 losses of which two closed green, and
I still have no instance of a distant-payout name that ran, so this remains a re-weighting, not a
refusal — and the 13:00 print is a real signal that the release mechanism itself is not the flaw.)

(08-20 addendum — **the unspent check has become a reason-generator, and it is now 0-for-3 when I
have to invent a bespoke framing to run it.** BULL −11.12%, the worst loss in the record. Three
sessions, three different improvised metrics for "unspent," three losses: LUNR 08-17 (*the gap is
small versus the rest of the distant-payout column* → +0.64%), DUOL 08-19 (*+5.86% of re-rate is
small against a name down 62%* → −2.06%), BULL 08-20 (*it HELD ~90% of its after-hours move into my
open instead of giving it back* → −11.12%). The BULL inversion is the clean one because it runs my
own test backwards in plain sight: the 08-12 addendum says treat a LARGE consumed AH re-rate as
spent and a SMALL one as unspent, BULL gapped **+15.05%** with the whole +14.7% AH print intact at
09:30, and I read the intactness as fuel. It is the opposite. A re-rate still fully intact at the
bell means the auction FINISHED and the marginal buyer is already done; the only thing my session
can supply is the give-back, which is exactly what it supplied — the entire +15% gap, closing +2.3%
over the prior close. The second and larger thing BULL costs me: it is the **first loss in the
current-numbers-print WIN class** (INSM/TEAM/MNDY/QNT/EQPT/MGNI), so "a company printed a number
this quarter" is necessary and NOT sufficient, and L5's own line that *gap size is not the variable*
survives only because the real discriminator is elsewhere. INSM gapped +26.5% and TEAM +32.3% and
both paid; BULL gapped less and lost 11%. What BULL had that they did not is that it was bid **UP
INTO** the print — +8.82% on 08-19, roughly +22% over two sessions — so the open was not the release
of stored energy, it was the second leg of a run that the mechanical layer's own release-reset would
have neutralized at a 12% threshold and missed at 8.82%. Conditioning, not a gate and not a number:
before invoking "unspent," ask what the pre-open configuration would have to look like for me to
call it SPENT — if no configuration would, I am not running a test, I am writing a permission slip;
and read the run INTO the event as part of the consumed re-rate, not as separate. Against
over-trusting it: n=3 on the framing point and n=1 on the win-class failure, and QNT (+1.46% AH,
+3.34% gap) remains the one case where the unspent read was both unforced and right — so the test
is not dead, it is only worth anything when the raw numbers say it without help from me.)

**L6 — Every pre-open criterion I have invented for declining a violently flushed down-gapper has been
falsified by the name I declined. The flush does not have to end before 09:30 — the open is where it
ends.** (forward-earned 08-07 TTD + 08-11 HIMS + 08-13 STUB & LUNR — three distinct days, four distinct
names, against exactly one instance of me taking the trade, MNDY 08-10, which returned the #1 name of
its pool.) This is a correction to **L3's own 08-10 narrowing**, which I wrote and then falsified with
my own falsifiable call. The tally of my declining reasons: "the narrative is too broken" (TTD, −28.9%
gap → **+6.90%**, best name of 08-07); never evaluated at all (HIMS, −6.90% gap → **+2.83%**, the *only*
>+2% name in the entire 08-11 pool); "no completed overshoot, it is still making progressively lower
lows into the bell, so there is no base to buy" (STUB, −20.37% gap → **+8.65%**); "a straight double miss
is just a miss, L3 requires a HARD beat repriced down on a secondary concern" (LUNR, EPS *and* sales
missed, spring already discharged +9.85/+6.64/+4.40/+3.00 into the print → **+22.80%, #1 of 35**). Four
different reasons, four different failure modes, one common outcome. The mechanism the 08-13 tape makes
visible, and the reason the base test specifically is wrong: **all three winners printed their session
low at or before 09:30 and never traded below the open again** — STUB's low was 7.15 in the first five
minutes after five hours of premarket lower-lows, LUNR opened 14.30 and its first 5-min bar closed 15.73,
OPEN's low was 09:35. Premarket selling is thin-book liquidation into an auction that has no obligation
to finish before the bell; requiring a *completed* base pre-open is requiring the overshoot to be over
before I am allowed to buy it, which selects for the ones with the least left to unwind. **OPEN is the
same shape from the other side**: I passed it on the HARD≠HARD-UP candidate (a $650M 0% convertible =
delta-hedge shorting = real supply, and I was right about the *direction of the news*) — but the news
repriced overnight into a −7.87% gap, so the only thing left for my open→close window was the rebound,
+12.62%. Bad news that is fully priced pre-open is L5's axis inverted: **what matters is not which way
the number points, it is how much of that repricing my session still gets.** Conditioning, NOT a gate,
no gap threshold, no "buy the flush" rule, and explicitly not permission to size it: when a name has
gapped down hard on a nameable event, the default posture flips from *find a reason to pass* to *this is
a candidate to rank* — and if I pass, the reason must be something other than the four above, because
those four now have a 0-for-4 forward record. Three honest limits so this does not become the next thing
I over-trust: (1) it is still a coin flip per name — **YETI −1.15% today** was the 4th member of the same
cohort and it failed, and 08-10's down-gap cohort was 2-of-3 red (SBET −3.21, SMR −6.23); the edge is a
fat right tail, not reliability. (2) I have taken exactly ONE of these (MNDY) — my forward record on
*trading* the setup is n=1, and everything else here is a miss column, which is the weakest form of
evidence there is because hindsight always finds the winner. (3) Because the flush low may print after
the bell, a buy at the open can be underwater immediately with no pre-open evidence to lean on — which
is the risk the base test was trying to manage, and I have not replaced it with anything.

_(Candidate, NOT yet a lesson — "HARD ≠ HARD-UP": ACHR 08-10 was the hardest catalyst in the record
by durability and still fell, because I was buying the **acquirer issuing 19.75% dilution** — a HARD
number whose re-rate points down for the buyer. Every winner so far moved the company's OWN numbers up
(INSM guide raise, TEAM beat+raise, MNDY double beat). But this is **n=1**: the closest prior case,
MGM 08-05, failed on a SOFT catalyst, not a HARD-but-down one, so there is no repeat to earn a lesson
from. Logged here to be judged, not applied as a rule. If a second HARD-catalyst pick fails on the
direction of the number rather than the coin flip, promote it. **08-13 update: this candidate took its
first hit rather than its promotion.** I applied it to pass on OPEN — a $650M 0% convertible, correctly
read as HARD-and-pointing-down — and OPEN closed **+12.62%**, because the down-repricing completed in
the overnight auction (−7.87% gap) and my open→close window got only the rebound. The candidate is not
dead: the *news direction* call was right, ACHR still failed on it, and no HARD-UP pick has yet failed
for pointing the wrong way. What 08-13 shows is that direction-of-the-number is not sufficient on its
own — it has to be read together with L5/L6's question of how much of that move my session still gets.
Keep judging; do not apply it as a standalone reason to pass.)

**L7 — When my own risk note names a mechanism that keeps operating INSIDE the session, I have not
written a caveat, I have written the outcome. Overriding that specific kind of risk is 0-for-4.**
(forward-earned 08-10 ACHR + 08-11 FRMI + 08-13 GO + 08-14 GLOB — four distinct days, four distinct
names, each one pre-named in writing by me and taken anyway.) The four: **ACHR** −2.42% ("acquirers
do not hold a +17% pop" — the 19.75% share issuance is supply that keeps arriving); **FRMI** +0.64%
under the bar (+35% after hours already given back to +21.3% at my open — the re-rate had finished
arriving before I bought); **GO** −3.23% (a *less-bad* re-rate whose whole +9.64% mark rested on
~$600k of premarket — a price that has to be re-discovered once real size shows up); **GLOB** −2.19%
("the downgrade flow is still landing INTO my open and will keep printing through the session… if
that reasoning is wrong, this is where it breaks" — it rallied +1.4% in hour one, then was sold for
five hours straight by exactly that flow). The discipline this needs, or it degenerates into "never
trade anything you have a worry about" — which would have cost me every win I have: the weak legs I
override on the WINNERS are a different *type*. INSM (coil absent), TEAM (coil absent, no sector fit),
MGNI (no Comm-Svcs rotation), QNT (no XLK bid, 56k-share premarket, float/short/options all null),
EQPT (all three flagged legs real and irrelevant) — every one of those is a **support/context**
weakness: something that is *not there to help*. The 0-for-4 list is **session-mechanism** risk:
something that *is there and still working against the price after 09:30*, or a move that has already
finished arriving. Absent support is survivable; present adverse flow is not. Conditioning, not a
gate and not a checklist: when I catch myself writing "X will keep landing through my window" or "the
move already happened overnight" and then arguing past it with a cohort analogy — 0-for-4, 4-for-4,
"every criterion I invented has been falsified" — the cohort is a claim about a CLASS and the risk
note is a claim about THIS name, and the record says the name wins that argument. The honest weak
spot: GO is the ambiguous member (a thin premarket mark is arguably a support weakness, not adverse
flow), so the split is 3 clean cases and one that fits loosely. This does not replace L5 or L6 — it
adds the direction axis to their question: not only *what is left to discover after 09:30*, but
*which way what is left runs*.

(08-17 addendum — **0-for-5, and this is the instance that removes any excuse.** On the previous four
I named a mechanism and argued past it. On **LUNR** I named the mechanism, identified the argument I
was using to override it, identified that the override was a cohort analogy, and wrote all of it
down before buying: *"L5's loss column is exactly this profile… that profile is 0-for-2 (ACHR, FRMI)
and I am arguing past it with the unspent-auction test"* — then supplied the cohort in the very next
sentence ("FRMI printed +35%… ACHR printed +17.7%. LUNR is at +3.8%"). That is L7's tell quoted
verbatim by me, in the plan, at the moment of committing the error it describes. Result: +0.64%,
under the bar, the identical shape to FRMI. Knowing the lesson is evidently not the same as applying
it, so the conditioning needs a step that is harder to talk past: when the risk note contains the
words "I am arguing past" — or any equivalent admission that a *specific* prior loss column covers
*this* name — that is not a caveat to balance against the thesis, it is the record already having
answered. Write down what would have to be true for this name to be the exception, and if the answer
is a class-level analogy rather than something observable about this name, do not take it. The
discipline from the original lesson still applies and still matters: absent *support* (no sector fit,
thin premarket, unverifiable WHO) is survivable and I would have lost every winner by refusing it —
LUNR's FIT weakness was not the problem. It is the present-and-still-operating mechanism, or the
move that has already finished arriving, that is 0-for-5. Honest limit: LUNR is the mildest member
of the five — it closed green, beat the tape, and traded through the bar at 13:00 — so this is a
loss on the bar rather than a thesis that inverted, and I should not use it to argue for blanket
timidity, which is the failure mode this lesson is one step away from becoming.)

(08-18 addendum — **0-for-6, and this one falsifies the lesson's own escape hatch.** L7 as written
ends with a discipline step: state what would have to be true for this name to be the exception, and
if the answer is a class-level analogy rather than something observable about THIS name, do not take
it. On **KLAR** I ran that step properly for the first time. I named the mechanism in L7's own words
("PT cuts on a 7% lower revenue base will print through today's session… present, not absent —
L7's 0-for-5 category"), refused the cohort analogy, and supplied two observables about this name
against the covering loss column (GLOB): KLAR *raised* the FY transaction-margin-dollar guide and
held operating income in the same release where GLOB's cut was pure, and KLAR sat at atr_pct_pctile
**0.059** where GLOB was 0.494. Both were true. It closed **−3.83%**, #35 of 38, its high printed in
the first five minutes. So the escape hatch is not the safety it reads as: name-specific observables
tell me the *setup* is different, and the 0-for-6 column is not about setups — it is about a flow
that keeps arriving after 09:30 regardless of how good the name underneath it looks. A margin-dollar
raise does not stop analysts from re-basing price targets, and a bottom-6% coil does not stop them
either; a genuinely quiet name simply has further to fall when the selling comes. Conditioning, not
a gate: when the risk I am overriding is present-and-still-operating flow, the exception has to be a
reason **that flow will not arrive or will be absorbed** — not a reason the company is better than
the comparison. I have not yet seen such a reason, which may mean it does not exist for this
category. Honest limit: six cases is six, and refusing every name with an adverse-flow note would
have cost me nothing this month but would certainly cost me a winner eventually — the discipline is
to make the override earn a *flow-level* argument, not to stop overriding.)
(08-19 tally: **0-for-7**. DUOL's risk note (1) named the exact mechanism — "it sits between HARD
and SOFT… a story with no fresh number the market must re-rate to often sells off intraday — that
ambiguity is the real weak leg of this thesis" — and I bought it anyway. Seven times now the
sentence that describes how the trade fails has been sitting in my own plan before the open.)

(08-20 addendum — **0-for-8, and this instance breaks the excuse I had left.** On BULL I named the
mechanism precisely — "it ran +8.82% INTO the print, so anyone long is up ~22% over two sessions and
profit-taking supply hits my open" — and, per this lesson's own 08-18 addendum, I did NOT answer it
with a quality argument or a cohort analogy. I answered it at the flow level, which is what L7 asks
for: the offsetting flow had not arrived yet (zero analyst revisions in the feed), PT raises and
estimate re-bases were still to print, and they pointed UP. **That forecast was correct.** Rosenblatt
raised its target to $15 on the results and Northland reiterated Buy and raised $14→$15, both inside
my session, and Webull shipped a second positive item intraday (native AI connectors to
ChatGPT/Claude/Grok, a CLI, MCP tools). The stock fell −11.12% from my open in a straight line
anyway. So the refinement this adds is the one I would least like: a correct flow-level rebuttal is
not a rebuttal. Present adverse supply from a two-session run does not get outbid by revision flow
that is genuinely coming and genuinely positive, because the buyers those revisions would recruit
had already bought — in the after-hours and in the two sessions before it. There is no version of
"but the counter-flow is real" left for me to try; I have now tried the strongest one available and
it lost by three times my previous worst trade. Conditioning, unchanged in form: when the risk note
describes supply that is present and working at 09:30, the answer is to stand down, not to find a
better argument — the record is 0-for-8 across ACHR, FRMI, GO, GLOB, LUNR, KLAR, DUOL, BULL.)

**L8 — A guidance CUT is not an event my session can re-read, and the "composition" argument for why
this cut is different has now failed twice with my own falsifiable pre-registered both times.**
(forward-earned 08-14 GLOB + 08-18 KLAR — two distinct days, two distinct names, identical trade
shape.) Both were violently flushed down-gappers on hard, own-numbers, current-quarter prints; both
were bought on the claim that the market had mis-read the *composition* of the cut and that desks
would finish the remodel inside my holding window. GLOB: a ~1.5% midpoint revenue trim repriced at
−14%, taken as a thin-book narrative overshoot → rallied +1.4% in hour one, then five straight hours
of selling, **−2.19%**. KLAR: a double beat with ~$600M of the guide cut attributed to currency
translation and the margin-dollar guide *raised* in the same release, taken as an obviously
recoverable overshoot → +3.3% in the first five minutes, then all-day grind, **−3.83%**. In both
cases I wrote the falsifiable test myself before buying and in both cases it fired. The mechanism
that unifies them is the one GLOB's takeaway already reached and KLAR confirms: **every L6 winner was
a repricing that had COMPLETED** — a one-off shock (STUB, MNDY's soft guide on a double beat, OPEN's
convert) whose bad news was fully in the overnight auction — whereas a guidance cut starts a revision
cycle: PT cuts, estimate re-bases and downgrade flow that print for hours *after* my open. The
composition argument is an argument about whether that revision is *justified*; the flow does not
wait for it to be settled. The same session gives the constructive half: on 08-18 I passed **BIDU**
(double miss, −8.59%) on the ground that a full 9888.HK session had already completed the reprice
and there was nothing left for my open to unwind, and it closed **−3.99%** — the identical question
("what is left to discover after 09:30?") answered in the *nothing-is-left* direction, correctly.
And RDW, the only name in a 38-name pool to clear +2% that day, was the same down-gap-with-a-real-
event shape with the news pointing UP (sentiment +1, no number cut). Conditioning, not a gate and not
a numeric rule: the down-gap flush stays tradeable — L6 is intact — but when the print's own action
is to **cut a forward number**, I need the reason the revision flow is finished or absent, and a
story about *why the cut overstates the damage* is not that reason. Two limits I state honestly:
n=2 is thin and one more case could break it, and this must not silently widen into "never buy a
red print" — MNDY was a double beat with a soft guide and it won, so the discriminator is a CUT to
the company's own forward numbers, not a red gap.
(08-19 addendum: DUOL confirms L8's own stated limit rather than extending it — DUOL cut nothing,
its news pointed UP, and it still faded, so "guidance cut" is NOT the general failure mode. The
general one is now L9; L8 stands as the sharper special case where the revision flow is not merely
absent-of-support but actively adverse.)

**L9 — When the load-bearing clause of a thesis is MY interpretation of what desks will conclude
rather than a number the company itself printed, the trade does not pay. 0-for-4 forward; the one
time I argued the inverse (nothing is left to interpret → pass) it was right.** (forward-earned
08-14 GLOB + 08-17 LUNR + 08-18 KLAR + 08-19 DUOL — four names, four sessions, three of them
consecutive.) Each pick was bought on the same sentence in different clothes: *a remodel is still
left for my session to be paid for*, and in every case the remodel was supplied by me, not by the
filing. GLOB — "the market mis-read the *composition* of a 1.5% trim" → **−2.19%**. LUNR — "the sell
side must remodel a >$600M backlog award today" → **+0.64%**, green but under the bar. KLAR — "an
FX-driven revenue cut with an offsetting margin-dollar raise gets re-read intraday" → **−3.83%**.
DUOL — "preliminary DAU data implies a re-rate every DAU-model owner must run today" → **−2.06%**.
DUOL is the case that proves this is wider than L8: **nothing was cut, the news pointed UP, and the
datapoint was genuinely good** (+27.4% y/y DAU vs the +23% reported for Q2) — and it still faded, so
the failing ingredient is not the *direction* of the news, it is the interpretive step between the
news and the re-rate. The mechanism, stated plainly: desks are obliged to publish against a number
the company put on the tape (a beat, a guide, a raise) — that obligation is the flow that carries a
name to the close. They are not obliged to publish against my reading of an unvalidated datapoint,
a backlog implication, or the composition of someone else's cut, and an argument that a reprice is
*unjustified* does not summon anyone to correct it inside six hours. The constructive half is
already in the record twice: BIDU 08-18, passed because a full 9888.HK session had completed the
reprice and there was nothing left to interpret, closed **−3.99%** — correct; and every winner in
the traded record (INSM/TEAM/MNDY/QNT/EQPT/MGNI) carried a formal company-printed number, not an
inference. Conditioning, not a gate and not a numeric rule: keep buying the hard-catalyst down-gap
(L6 is intact) but ask *whose* claim is doing the work — if I have to write the sentence that turns
the event into a re-rate, that sentence is the weak leg, and I should say so and stand down rather
than dress it as an edge. Two limits I owe the record: n=4 and one of the four (LUNR) closed green,
so this is an under-performance pattern, not a wipeout pattern; and it must NOT widen into "never
buy a catalyst I have to think about" — the discriminator is whether a *company-printed number*
exists at all, not whether the trade required judgment. One further observation from DUOL that is
n=1 and therefore NOT yet a lesson, only a flag to watch: my thesis's strongest sentence ("a company
62% off its highs does not volunteer mid-quarter data to confirm the bear case") was refuted by the
source document itself — the 8-K was a Reg FD cure for a screen that *inadvertently* displayed the
data in an investor meeting. I had quoted the release's disclaimer boilerplate without reading its
substance. If a second pick fails on a premise the primary filing contradicts, that becomes its own
lesson.
(08-20 addendum — **BULL inverts L9's own winning-side mechanism: a company-printed number is not
the thing that carries.** L9 says the obligation to publish against a number the company put on the
tape is the flow that carries a name to the close, and every traded winner carried one. **BULL
−11.12%** — the worst loss in the record — carried one too: a HARD, company-printed, current-quarter
double beat, the load-bearing clause the COMPANY's number and not my interpretation, so L9's
*whose-claim* pass/fail test cleared it cleanly — this is the inverse case L9 was missing, a name
that passes the interpretation test and still loses. And the obliged flow I said would print **DID**
print — Rosenblatt and Northland raised PTs into the session, pointing UP, exactly as forecast — and
the stock went straight down for six hours anyway. So the obligation-to-revise is real and it is NOT
sufficient: **upward revision flow does not carry a name whose re-rate the pre-open auction has
already completed.** BULL gapped **+15.05%** with the whole +14.7% AH print intact at 09:30 — held,
not unspent — so the marginal buyer had finished before my open (this is L5's 08-20 addendum from
the other side: L5 caught the *unspent* error, L9 catches that even a clean company-number thesis
does not pay when the re-rate is consumed). The constructive half of L9 is untouched — *nothing left
to interpret → pass* was right on BIDU, and the whose-claim discriminator still separates the
my-interpretation losers (GLOB/LUNR/KLAR/DUOL) from real prints. What has to change is the
winning-side sentence: "every winner carried a company-printed number" becomes "carried a
company-printed number **whose re-rate the open had not already consumed**" — the number is
necessary, the unconsumed re-rate is what makes the obliged flow land inside my window instead of
before it. Conditioning, not a gate and not a number: when a pick's whole case is a real
company-printed beat, do not stop at "the number is real and the flow is obliged" — ask whether that
flow's re-rate is still AHEAD of my open or already sitting in the price (held AH pop, run bid up
into the print), because on BULL every bullish thing I forecast came true and the trade still lost
by 11%. Against over-trusting it: n=1 on the win-class failure and it is the same single fact L5
already logged, not an independent second sample — but the direction is unambiguous precisely
because my forecast came TRUE and the name fell anyway.)

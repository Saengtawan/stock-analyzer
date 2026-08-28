# Overnight-catalyst experiment — forward record (OFF-RECORD, separate from resonance)

**What this is:** an experiment separate from resonance/exec_ai/swing. The idea (user's): the biggest,
freshest catalyst is often an **after-hours earnings/news print**; buying to capture the **overnight gap**
into the next open may beat resonance's open→close window (which historically gets the give-back).

**Isolation (hard):** this record lives ONLY here. It is NEVER written to resonance's `data/*.db`,
`resonance/plans/`, or any live journal, and its picks do not enter resonance's forward record. Keeping
it out is the whole point — do not let it contaminate the resonance data.

**Method (same discipline as resonance):**
- The AI reads **context/odds** pre-print (positioning, run-up-into-print, beat history, comps, the
  expectations bar) — it does NOT claim to predict the earnings outcome (that direction is ~coin-flip).
- Two ways to play, both logged: **BET-BEFORE** (buy before the print on the odds — a gamble) vs
  **WAIT-AFTER** (let it print, read the fresh reaction, buy AH only if it's a clean beat that HELD —
  the disciplined version; screens out beat-but-cut / sell-the-news like KLAR / WDAY).
- Grade each at **next-day open (and/or the AH move)**: did the overnight hold pay?

**Honest priors going in:** overnight gap-prediction is closer to a coin flip than the intraday
hard-beat edge. The scoreboard is whether **overnight-AH-catalyst** actually beats resonance's
**open→close** over a real forward sample. Nothing sized up without that proof.

---

## Record

| # | date (Thu) | name | context / odds (pre-print) | play | print result | overnight → next open | edge vs "buy at open" | note |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-08-20 | ROST | −6% into print (not extended, room), strong beat history, BUT sector weak (TJX −6.9/BURL −4.1); expected move ~4-8%; odds ~55/45 | bet-before | **BEAT** — buy pre-close 229.34 → **sell end-of-AH 248.75 @19:59 ET = +8.46%** (GRADED) | user sold in AH — realized the pop | **end-of-AH +8.46%** vs premkt-before-open +6.28% vs open +6.33% — the AH pop was the BEST exit; holding overnight gave ~2pp back | ✅ WIN, and the correct execution — sold the AH pop instead of holding into the open (the BULL lesson). All three exits now recorded to compare forward. n=1 coin-flip landed heads |

_(append one row per overnight idea; grade at next-day open. Screened-out names worth noting:
WDAY 08-20 — beat but faded AH = sell-the-news, correctly avoided.)_

## Blind-prediction test (08-20, replay) — what the setup-odds read actually did

A blind pre-close replay of 08-20 (predict from SETUP only, results withheld) called, in order:
**OSIS ~57/43 up, ROST ~55/45 (contaminated — the result leaked, flagged), BEKE ~50/50.** Actual AH:

| pick | pre-print odds call | actual AH move | clean? |
|---|---|---|---|
| **OSIS** | ~57/43 lean UP (beat-and-raise history, defense tailwind, reasonable bar) | **−14.94%** 🔴 | clean — and WRONG, hard |
| ROST | ~55/45 up | +8.46% | contaminated (result leaked into a search) |
| BEKE | ~50/50 | +0.67% | clean — flat |

**Read (data, for the brain to weigh — not a verdict imposed on it):** the one genuinely-clean confident
call, OSIS, went the opposite way and crashed −15%. On this single blind sample the setup-odds read did
NOT predict direction; ROST last night was the result leaking + the coin landing up, not a demonstrated
skill. n is tiny — let the forward record keep testing whether any setup edge shows up before sizing.

## 2026-08-21 — ABSTAIN (0 picks), and a cron-timing bug

The run fired at Thai 07:45 = **ET Thu 08-20 20:44** — ~4.8h AFTER Thursday's close and after the
20:00 AH session ended (verified: `TZ=America/New_York date` and yfinance's last prepost bar
2026-08-20 19:59 for both ROST and SPY). It was briefed as a pre-close 15:15-15:50 pass. It was not
one, so no pre-close read was manufactured.

Separately, **Friday 08-21's after-close field is empty**: the only confirmed AMC names are NIBE-B.ST
(Stockholm, not US-AH tradeable) and SHAZ (micro-cap, paper-thin AH book). Friday's real reporters
(UI, BJ) are all BEFORE the open — wrong side for an overnight hold. This is structural, not bad
luck: US companies don't report Friday night, and the few that do are burying something.

**Fix:** cron must fire ET 15:15-15:50 = **Thai 02:15-02:50**, and Mon-Thu only.

ROST (08-20) remains **ungraded** — grade() correctly returned 0 because the 08-21 open hasn't
printed. AH last 248.75 vs 229.34 entry; the thesis question is how much of that gap survives to the
open. Not a win until graded.

### 2026-08-21 — pre-close re-run (13:09 ET) with the WIDER field: still ABSTAIN, now evidenced

This run applied the new Friday rule (next trading session = **MONDAY**, not "tomorrow") and searched
the Monday-BMO + weekend-catalyst legs the earlier run never looked at. Field, verified:

| name | catalyst (verified) | setup read | call |
|---|---|---|---|
| **PDD** | Q2 **Mon 08-24 BEFORE the open** (company PR, call 07:30 ET) — the ONLY liquid confirmed Monday-BMO name | not extended (−4% from 20d hi) **and** held flat −0.4% while BABA fell −7.1% on its miss today = real relative-strength tell. BUT peers sold (JD beat→sold, BABA −7%) and its own print-gap base rate is **0-for-4, all down** | **~30/70 against — PASS** |
| **CAPR** | PDUFA **Sat 08-22** (verified live) | AdCom **9-3 AGAINST** (Jul 29); +58% spike 08-14 on the amendment lifeline has **faded** (−6.3% 5d, −8.9% today, now below the spike close). Amendment ⇒ likely *extension*, already priced | **~30/70 against — PASS** |
| SVRA | Aug 22 PDUFA | **VERIFIED EXTENDED to Nov 22, 2026** (major amendment) | off the table |
| HEI, SMTC | aggregator said Mon 08-24 | **VERIFIED FALSE — both report Tue 08-25 AMC** | off the table |

**The deciding data — PDD's own earnings-gap base rate (yfinance, 2y daily):**

| print date | overnight gap | full day |
|---|---|---|
| 2024-08-26 | **−21.21%** | −28.51% |
| 2024-11-21 | **−10.35%** | −10.64% |
| 2025-05-27 | **−17.63%** | −13.64% |
| 2026-05-27 | **−8.23%** | −10.38% |

Every large UP gap in the same window (+5.9 / +12.0 / +8.8 / +7.1) is a China-stimulus or tariff-news
day — **not one earnings gap-up in two years**, average print gap ≈ −14%.

**Self-correction worth recording:** the first read of PDD was "~52/48 lean UP" off the relative-strength
tell (flat while BABA −7%). The base-rate pull reversed it to 30/70 against. The tell was real; it just
loses to a 0-for-4 record and a sector selling every print this season. This is the setup-odds read
*working* — it talked itself out of a bad bet on data, rather than into one.

**Structural finding (carry forward): Friday runs are near-dead by construction.** No US AMC reporters
⇒ no same-evening AH play at all; the Monday-BMO substitute is a **3-day weekend hold** with un-exitable
gap risk — a materially worse bet than the one-evening ROST shape the strategy is built on. Either skip
the Friday pre-close pass or run it purely as a Monday-BMO scout with a **higher** bar.

Plan: `overnight/plans/2026-08-21.txt`. 0 picks logged (no `journal.log` calls). Nothing written to
resonance / exec_ai / swing.

### 2026-08-21 — pre-close pass #3 (13:45-14:05 ET): ABSTAIN confirmed, field WIDENED

Third pass today, run in the actual pre-close window. It did **not** just re-affirm the 13:09 run —
it searched the Monday-BMO leg properly and found **two names the earlier pass never looked at**
(XPEV, NSSC), pulled every candidate's own print-gap base rate from yfinance, and re-verified the
Friday AMC calendar and the SVRA date from source. Verdict unchanged: **0 picks.**

**Full Monday 08-24 BMO field (verified):** NCTY, NSSC, PDD, XPEV, XYF.

| name | the deciding data | call |
|---|---|---|
| **XPEV** | Mon 08-24 BMO **08:00 ET call VERIFIED** (company PR/CnEVPost) → real premarket exit. ~$75M/day = the ONE liquid premarket exit in the field. Not extended (−9.1% from 20d hi). Own gap base rate **7up/4down, mean +0.68%**. Q2 deliveries already public (monthly reports) ⇒ surprise narrowed to margin+Q3 guide; deliveries +0.11% YoY = flat | **~53/47 lean UP — PASSED on sizing:** +0.7% edge < ±3% weekend gap noise |
| **NSSC** | Best paper edge: **8up/4down, mean +2.58%**. But **0.2M sh/day (~$7.6M)** → 08:00 print sells into a 2-5% premarket spread; tails −20.2/−14.5 | **PASS — exit not executable** |
| **PDD** | 3y pull, last 8 prints: **1 up / 7 down, mean −7.84%** | **~30/70 against — PASS** |
| NCTY | **+21.6% today, +65% 20d**, 0.3M sh/day — maximally extended into its own print | PASS |
| XYF | ~0 volume | PASS |
| CAPR | PDUFA Sat 08-22 verified live, but AdCom **9-3 AGAINST**; spike faded below its close. ~25-30% approval, −50%+ on CRL | **negative EV — PASS** |
| SVRA | **re-verified: EXTENDED to Nov 22 2026.** Aggregators still listing Aug 22 are STALE | off the table |
| index adds | S&P DJI latest (Aug 13): RDDT eff. Aug 18, SUI eff. Aug 20. **Nothing effective Monday** | none available |

**Correction to yesterday's entry:** it recorded PDD as "0-for-4, all down". The fuller 3y pull is
**1-for-8** (+2.89% on 2026-03-25 is the lone up-gap). More data, same conclusion, stronger case.

**Friday AMC re-verified from calendar:** only NIBE-B.ST (Stockholm, no US AH book) and SHAZ
(micro, paper-thin). **Zero tradeable US AMC reporters** ⇒ the same-evening AH play — the ROST
shape this strategy is built on — did not exist tonight, by calendar, not by opinion.

**Why this is a real abstain, not a flinch:** every name dies on its own named evidence (base rate,
adverse AdCom, unexecutable exit, extended-into-print, zero volume), and the one name that reached
the final test — XPEV — failed a *sizing* test, not a belief test: a +0.7% expected edge does not
pay for 65 hours of un-exitable weekend exposure. Tape was calm (SPY +0.41%, VIX 15.30), so this
was not a fear-of-tape call. And weighed against **this record**: the setup-odds read has not shown
direction skill (OSIS clean ~57/43 UP → **−14.94%**; ROST contaminated), so it must demand MARGIN
before betting. XPEV at ~53/47 is exactly the thin edge the record says can't be called reliably.

**Scout / counterfactual, deliberately NOT logged:** XPEV Fri close **$12.12**, prints Mon 08:00 ET.
Check Monday premarket 08:00-09:29 vs 12.12 — **gap ≥+3% ⇒ the "edge too small" judgment was wrong**
and the Monday-BMO leg deserves a lower bar; **within ~±1.5% ⇒ the pass was right.** Logging it
would put a bet I don't endorse into the win-rate, so it's tracked off-record on purpose.

**Carry forward (2nd confirmation):** Friday pre-close runs are near-dead by construction — no US
AMC reporters ⇒ no same-evening play; the Monday-BMO substitute needs a **higher** bar (edge must
beat weekend gap noise AND have a liquid premarket exit). Today only XPEV reached test two, and it
failed test one.

Plan: `overnight/plans/2026-08-21.txt`. 0 `journal.log` calls. Nothing written to resonance /
exec_ai / swing.

### 2026-08-21 — pre-close pass #4 (13:57-14:20 ET): ABSTAIN, and the WEEKEND-FDA leg finally searched

Fourth pass today. It did **not** re-run pass #3's searches — it opened the one leg no pass on this
date had touched, the **Aug 22/23/24 FDA decision calendar**, and closed it on evidence. Also pulled
the Friday AMC list from the calendar page itself (3rd independent confirmation) and re-checked every
Monday-BMO name against live tape. Verdict unchanged: **0 picks.**

**Tape (13:57 ET):** SPY 765.55 +0.39%, QQQ +0.33%, IWM +0.69%, **VIX 15.27 −4.62%**. Calm — not a
fear-of-tape abstain.

**NEW: the weekend PDUFA leg — three items, all dead:**

| name | the deciding data | call |
|---|---|---|
| **RARE** | PDUFA was Sat 08-23 — but FDA granted accelerated approval **Aug 19, FOUR DAYS EARLY** (GENGLYCOS, first-ever GSDIa therapy). Tape tells the rest: 08-19 close 26.24 → **08-20 open 28.39 (+8.2% gap) → low 25.04 → close 25.32**, a full sell-the-news round trip closing *below* the pre-approval close; 08-21 26.06 basing. Who-buys: flow **arrived and was consumed** Thursday at the open | **catalyst FIRED — PASS** |
| **SVRA** | MOLBREEVI PDUFA was Sat 08-22 — **re-verified a 3rd time: EXTENDED to Nov 22, 2026**. Aggregators printing "Aug 22" are STALE | off the table |
| **BIIB** | SC lecanemab *starting dose* PDUFA **Mon 08-24**. (1) **Exit mechanism fails** — action date is Monday itself, FDA acts during/after the session, but my exit is Monday *premarket*: 65h of weekend risk for an event that hasn't fired by the sell. (2) Label extension on an approved drug, no AdCom, high-probability ⇒ priced, and small vs a $32B cap | **PASS** |

**Friday AMC, confirmed from the calendar page (digrin 08-21): "11 reports, 2 before open, 2 after
close, 7 TBD"** — the two AMC names are **NIBE-B.ST** (Stockholm, no US AH book) and **SHAZ** (micro,
paper-thin). **Zero tradeable US AMC reporters** ⇒ the ROST shape did not exist tonight.

**Monday BMO re-checked on live tape:** XPEV 12.15 (+1.21%, −9.1% from 20d hi, 7up/4down mean +0.68%,
08:00 ET call, the one liquid premarket exit) — **re-affirmed the sizing pass**: a +0.68% mean edge sits
*inside* the ~±3% weekend-gap dispersion. NSSC 37.98 (best paper edge 8up/4down +2.58%, but 0.2M sh/day
⇒ **exit not executable**). PDD 88.86 (1-up/7-down last 8, mean −7.84%). **NCTY 5.32 — +22.02% TODAY**,
+65% 20d, thin, reporting Monday BMO = maximally extended into its own print. XYF ~0 volume.

**Non-print leg, judged on its own terms — and the one honest near-miss:** the **Jackson Hole**
symposium runs Aug 21-23 with Powell's address apparently **Saturday 08-22** (this morning's coverage
still had the market "waiting on Jackson Hole"). That is a **genuine weekend-gap mechanism** — arguably
the only real one in the field, and index premarket *is* exitable Monday before the open. It still
yields no pick, for a reason rather than a rule: **zero direction edge** on a Fed speech (the purest
coin flip on the board — no setup to read), and **VIX 15.27 falling −4.6% into it** = a small priced
move to split 50/50. Recorded honestly: **searches on the 2026 speech date came back heavily
contaminated with Aug-2025 Jackson Hole coverage**, so the Saturday timing is *not cleanly verified* —
and I won't bet on a fact I couldn't confirm. Flagged for the next run.

**Why this is a real abstain:** every name dies on its own named evidence — RARE fired early and was
sold (price data), SVRA extended, BIIB's event lands *after* my exit, NCTY +22% into its print, NSSC
unexecutable, PDD 1-for-8, XPEV failed **sizing** not belief, Jackson Hole real-mechanism/no-edge. And
weighed against this record: the setup-odds read still has no demonstrated direction skill (OSIS clean
~57/43 UP → **−14.94%**; ROST contaminated), so it must demand MARGIN. XPEV at ~53/47 is exactly the
thin edge the record says can't be called. Betting it would be manufacturing a pick to avoid a third
blank line.

**Carry forward (3rd confirmation): Friday pre-close runs are near-dead by construction.** No US AMC
reporters ⇒ no same-evening play; the Monday-BMO substitute is a 3-day hold needing a **higher** bar
(edge > ±3% weekend noise AND a liquid premarket exit). Skip the Friday pass, or run it as an explicit
low-expectation Monday-BMO scout. Cron fix stands: **ET 15:15-15:50 = Thai 02:15-02:50, Mon-Thu only.**

**Scout, still deliberately NOT logged:** XPEV Fri close **12.15**, prints Mon 08:00 ET. Monday
premarket 08:00-09:29 vs 12.15 — **≥+3% ⇒ the sizing pass was wrong** and the Monday-BMO leg deserves a
lower bar; **within ~±1.5% ⇒ right.** Kept off the win-rate on purpose.

Plan: `overnight/plans/2026-08-21.txt`. 0 `journal.log` calls. Nothing written to resonance / exec_ai /
swing.

## 2026-08-24 (Mon) — pre-close pass (13:06-13:40 ET): ABSTAIN (0 picks), and the XPEV pass SCORES

**Tape:** SPY 764.20 −0.20%, QQQ 708.60 −0.68%, VIX 15.68 (+3.6%). Calm — not a fear-of-tape abstain.

### The carried XPEV counterfactual is RESOLVED — and the abstain discipline just earned its keep

Friday declined XPEV at ~53/47 on **sizing** (+0.68% mean edge vs ±3% weekend-gap noise) and logged a
falsifiable test: ≥+3% ⇒ pass was wrong; within ±1.5% ⇒ pass was right. **Actual (yfinance, 307
premarket 1-min bars): XPEV 12.15 → last premarket print 11.75 = −3.29%** (premarket range 11.28-12.77,
RTH open 11.83). It gapped the OTHER way, harder than the threshold. The pass didn't just skip a thin
edge — it **avoided a −3.3% overnight loss**. First evidence in this record that "demand MARGIN" has
positive value, and the reason the bar stays high below.

### Leg A — tonight's AMC (the ROST shape): structurally dead, second confirmation

Two independent calendars agree (eOption: "PICS TUYA"; digrin: 114 companies, 4 BMO / **1 AMC** / 109
TBD). I resolved the liquid names hiding in the 109-name TBD bucket by yfinance timestamp rather than
trusting the aggregators: **WDS** ($13.9M/day, 08-24 16:00 ET, but an Australian filer releases ~19:30 ET
= the edge of my 19:59 sell, and an energy major's H1 is low-surprise), **AVXL** ($2.7M/day), **PICS**
($4.9M, n=2 history), **TUYA** ($0.8M/day, sub-1% gaps). **PVH** is 09-02, not this week. **Zero AMC
reporters tonight with a book deep enough to sell into.**

### Leg B — Tuesday BMO (one-night hold, premarket exit). Every base rate pulled:

| name | own print-gap base rate (last 10) | call |
|---|---|---|
| **DKS** | **4up/6down, mean −0.00%, med −2.52%**, 5 of last 6 DOWN | finalist → **~48/52 PASS** |
| **CTRN** | 8up/2down, **mean +6.48%, med +7.93%** — best on the board | **killed twice, below** |
| BZ / VIPS | 3up/7down −0.98% · 4up/6down −0.58% | PASS |
| BNS / BMO | ~5up/5down, ±1-2% moves | no magnitude — PASS |
| EH / SLQT / TOUR | fat tails but $2.8M / $0.5M / ~$0M/day | exit unexecutable — PASS |
| GFI | **+43.4% in 20d, AT its 20d high**; direction is really the gold tape | extended into print — PASS |

**CTRN is the one I wanted, and it dies on two verified facts.** Its six straight up-gaps
(+2.14/+16.48/+8.73/+11.91/+22.35/+15.0) all **fade hard intraday** (−8.24/−11.86/−4.40/−9.45) — a
perfect fit for a strategy that sells in premarket and skips the fade. But (1) **the catalyst already
fired**: on ~Aug 18 Citi Trends **PRE-ANNOUNCED** preliminary Q2 sales +10.9% to $211.6M, comps +10.5%
(company IR/8-K) — the sales surprise that *drove* those gaps is already public, and the stock is
+13.6% in 20d, −2.7% off its 60d high, i.e. already paid. Same shape as RARE. (2) **The exit doesn't
exist**: CTRN printed **zero premarket bars on 08-21 and zero premarket volume on 08-24**. Same kill
as NSSC.

**DKS — reached the final test, and the Q1 tell decides it.** Verified Tue 08-25 BMO, 8:00 ET call
(company PR + yfinance timestamp agree), **$283-291M/day = the only genuinely liquid premarket exit in
the field**, one night, no weekend. Setup is genuinely attractive: **179.13, just 1.98% above its
52-week LOW**, −26.7% off the 52-wk high, −9.2% in 5d, through multi-year support; the last leg down was
**JD Sports sympathy** (UK rival cut outlook), not DKS news; FY EPS guide $13.50-14.50 reaffirmed; and
peer **ROST — this record's own winner — gapped +6.3% from the same "washed-out retailer" archetype**.
Against that: the gap is what I actually harvest and its **expected value is ~zero with a −2.52%
median**, and — decisively — **at the May print DKS delivered a 6% comp BEAT and RAISED guidance and
still fell ~6%**, on $96.5M of Foot Locker integration costs. The market's objection isn't "can they
beat," it's Foot Locker — and Q2 loads *more* of it (rev +54.6%, EPS −13.2%). That is exactly the
"needs a PERFECT print" shape the method says is the weaker bet. **The ROST analogy does not carry:
ROST's low bar was cyclical with no overhang; DKS's is a thesis problem the market has already punished
through a beat-and-raise.** Same costume, different setup.

### Leg C — FDA. **This corrects Friday's record on BIIB.**

Friday declined BIIB on *exit timing*, treating the Aug-24 lecanemab SC starting-dose PDUFA as a live
Monday catalyst. Wrong reason — **the catalyst was never live: FDA approved LEQEMBI IQLIK subcutaneous
as an initiation dose on JULY 13, 2026, six weeks ahead of the action date** (Biogen IR); launch expected
late August. The RARE shape a second time. Tape agrees: BIIB 214.61, −1.0%, no coiled event.
**JAZZ** (Ziihera PDUFA Aug 25) fails twice: the FDA acts *during/after Tuesday's session* while my exit
is Tuesday **premarket** — the event hasn't fired when I sell — and NEJM Phase 3 (~35% PFS reduction,
OS 26.4 vs 19.2mo) on a drug already accelerated-approved ⇒ high probability ⇒ priced. **SVRA** still
extended to Nov 22 (4th confirmation).

### Leg D — non-print. NVDA is the live theme (NVDA −6.6%/5d, QQQ −2.9%, VIX +3.6% = de-risking) but it
**reports Wednesday AMC** — buying today and selling Tuesday premarket captures none of it, only drift.
No gap mechanism into Tuesday's pre-open ⇒ PASS. **Jackson Hole is now moot** (symposium ran Aug 21-23;
the reaction is in today's tape, behind my window) — Friday's un-verified-timing flag is closed.

**Why this is a real abstain:** every name dies on its own named evidence — no tradeable AMC book,
CTRN's catalyst pre-announced + zero premarket volume, GFI extended, BIIB approved early, JAZZ firing
after my exit, negative gap base rates, and DKS failing on a demonstrated same-company precedent. And
weighed against this record: OSIS (clean ~57/43 UP) printed −14.94%, ROST was contaminated — the
setup-odds read still shows **no** direction skill — while the *passes* are now scoring (XPEV −3.29%).
DKS at ~48/52 has no margin. **I state the cost plainly: three straight blanks = no forward data. The
fix is a better calendar, not a looser bar.**

**Scout, deliberately NOT logged** (same method that just validated on XPEV): DKS Mon close **179.13**,
prints Tue 08:00 ET. Tuesday premarket vs 179.13 — **≥+4% ⇒ my "needs a perfect print" read was WRONG**
and a 52-week-low washout should outrank a bad gap base rate; **≤−2% or within ±2% ⇒ the pass was right.**

### ⭐ STRUCTURAL FINDING (revises the cron): **MONDAY IS NEARLY AS DEAD AS FRIDAY**

Same cause as Friday — US companies don't report Monday night. Confirmed across two calendars plus
per-name timestamp resolution: 1-2 genuine AMC reporters, **none above $13.9M/day**. The AMC density is
**TUE/WED/THU** — tomorrow proves it (Tue 08-25 AMC: **INTU, ZM, HEI, SMTC, BOX, NCNO, QFIN, JOYY, NOAH**,
real books), and Wednesday has NVDA.

**Cron revised (was Mon-Thu): ET 15:15-15:50 = Thai 02:15-02:50, TUE-THU only.** Monday and Friday
pre-close passes should be skipped or run explicitly as low-expectation next-session-BMO scouts.

Plan: `overnight/plans/2026-08-24.txt`. **0 `journal.log` calls.** Nothing written to resonance /
exec_ai / swing.

## 2026-08-26 (Wed) — 2 PICKS: **NVDA ~55/45** + **OKTA ~57/43** (first non-abstain since 08-20)

**Timing note:** the run fired **13:23 ET**, not the briefed 15:15-15:50. Prices below are 13:26 ET
marks; the user buys near the close, so grade against the actual fill, not these.
**Tape:** SPY 765.45 −0.06%, QQQ −0.02%, VIX 15.55 (+0.65%). Calm — not a fear-of-tape read either way.

### The structural finding reverses: **WEDNESDAY IS THE DENSE NIGHT**

Fri 08-21 and Mon 08-24 abstained because the calendar was **empty** (zero US AMC reporters with a
tradeable book — three passes confirmed it). Tonight, verified by yfinance earnings timestamps rather
than aggregators: **NVDA, CRM, CRWD, VEEV, HPQ, OKTA all print 16:00 ET**, every one liquid. ADSK is
08-27, SNOW/NTAP 09-02, ANF is BMO. No PDUFA dated today, no index add effective tomorrow. The
Tue/Wed/Thu density prediction from the 08-24 entry is confirmed.

### The whole field, with the data that decided each

| name | px | $/day | 5d | 20d | from 20d hi | own print-gap base rate (last 10) | call |
|---|---|---|---|---|---|---|---|
| **NVDA** | 210.17 | $23.8B | −3.4% | +10.6% | −7.8% | **6up/4down, mean +2.94%, med +2.83%** | **PICK ~55/45** |
| **OKTA** | 129.26 | $359M | −8.5% | **−5.6%** | **−17.4%** | **7up/3down, mean +4.10%, med +6.41%** | **PICK ~57/43** |
| VEEV | 246.44 | $388M | −1.8% | **+18.5%** | −2.8% | 6up/4down, mean +2.27%, med +5.87% | PASS — extended |
| CRM | 203.67 | $2.2B | −1.2% | +8.1% | −4.5% | 6up/4down, **mean −1.16%, med +0.52%** | PASS — zero EV |
| CRWD | 188.16 | $1.5B | −6.6% | +5.0% | −17.2% | **2up/8down** (last SIX straight down) | PASS |
| HPQ | 29.58 | $376M | −1.2% | +4.1% | −8.1% | 3up/7down, mean −1.99% | PASS |

**NVDA ~55/45 lean UP.** Not extended into its own print — and the sharpest version of that: previews
written days ago quote NVDA at **$225 with an implied lower bound of $209.56**, and it is trading
**210.17**, i.e. already AT the downside the options implied. The de-risking happened *before* the
print. The bar is low on the biggest swing factor: consensus $92.07B rev / $2.09 EPS vs the company's
own **$91.0B ±2% guide = only 1.2% above the midpoint**, and guidance still assumes **ZERO China
data-center revenue** while FT reports H200 shipments to ByteDance/Tencent have already started
(~10k each). 13 straight beats. Implied move **5.4% vs the 12-quarter average swing 7.4%** = options
price a quiet print. And the exit fits the name's own pattern: NVDA's **gap is repeatedly better than
its full day** (2025-02 gap +2.83 → day −8.48; 2025-11 +5.06 → −3.15; 2026-02 −0.66 → −5.46), so
selling the AH pop is exactly the trade that dodges the fade this record keeps observing.
**Wrong if:** the **17:00 call's Q3 guide** (not the Q2 number) disappoints — sub-$100B or a margin/supply
wobble sells it off through a beat, the KLAR/WDAY shape. Secondary: **gap decay is real** — the last
four prints averaged only **+0.86%**; the market has learned to fade this, so a beat may pay nothing.

**OKTA ~57/43 lean UP.** The two things that rarely co-occur: the **best base rate on the board**
(7up/3down, mean +4.10%, median +6.41%) on the **most washed-out name in the field** — the only one
negative on 20 days (−5.6%), −8.5% in 5d, −17.4% off its 20d high. And expectations are being
**reconfirmed, not cut**: consensus $0.96 / $793M held through the last 30 days, with **upgrades from
Wells Fargo and Citizens** into the print and an average PT of **$146.34 vs $129 spot**. The bear point
— revenue growth decelerating 12.7% → 8.9% — is the *consensus* story, i.e. what the −17% drawdown is
already paying for. That makes it the "gaps on a merely-fine print" shape rather than the
"needs a perfect print" shape the method says is the weaker bet. Options price an ~11% move.
**Wrong if:** billings/cRPO come in soft — its own last 10 contain **−14.01 / −13.03 / −7.66** gaps.
And the AH book ($359M/day) is real but far thinner than NVDA's; the 19:59 spread costs something.

**VEEV was the near-miss and it dies on positioning, not on a rule:** a good base rate (median gap
+5.87%) and a habitual beat-and-raise, but **+18.5% in 20 days and only −2.8% off its 60d high** =
maximally extended into its own print, and its two worst gaps (−9.88, −7.67) both came off run-ups.
Taking it would have been filling a slot. **CRWD** is genuinely washed out (−17.2%) — attractive — but
the **gap is what I harvest and it has gapped DOWN 8 of 10, the last six straight**; the full-day often
recovers, which is irrelevant to a 19:59 exit. Same kill as PDD's 1-for-8.

**Honest frame.** This record's own evidence still says the setup-odds read has **no demonstrated
direction skill** (the one clean confident call, OSIS ~57/43 UP, printed **−14.94%**; ROST was
contaminated) while the **passes have scored** (XPEV −3.29%). That is why the bar killed four of six
names tonight and why I take two, not three. But the three straight abstains were caused by an
**empty calendar**, not by a high bar — abstaining into the densest AH night of the quarter would be
flinching, not discipline. These are thin leans, ~55/45 and ~57/43, not convictions. Nothing sized up.

Plan: `overnight/plans/2026-08-26.txt`. **2 `journal.log` calls** (NVDA 210.17, OKTA 129.26; ah_mark
empty — `grade()` fills it from the ~19:59 ET mark tonight). Nothing written to resonance / exec_ai /
swing.

## 2026-08-26 GRADED — **both picks WON**: OKTA **+25.68%**, NVDA **+4.45%**

`grade()` filled both from the ~19:59 ET end-of-AH mark vs the pre-close entry.

| pick | odds called | entry | end-of-AH sell | result |
|---|---|---|---|---|
| **OKTA** | ~57/43 lean UP | 129.26 | — | **+25.68%** ✅ |
| **NVDA** | ~55/45 lean UP | 210.17 | — | **+4.45%** ✅ |

The reads that carried them were the ones stated in advance: OKTA's "best base rate on the most
washed-out name" (7up/3down, med +6.41%, −17.4% off its 20d high) and NVDA's "already trading AT
the options-implied downside (209.56) before the print." NVDA's next-day confirmation: it opened
+6.02% and is **+9.13% on 08-27** — i.e. holding would have paid MORE this time, the opposite of
ROST. Worth watching: the record now has one case where end-of-AH was the best exit (ROST, +8.46
vs +6.33 at the open) and one where it left money on the table (NVDA). Two data points, no rule yet.

**Record: 3-for-3 graded (ROST +8.46, OKTA +25.68, NVDA +4.45).** Stated honestly: n=3 with two on
a single night, and the one clean blind call this record ever made (OSIS ~57/43 UP) printed −14.94%.
Three wins is three wins, not demonstrated direction skill.

## 2026-08-27 (Thu) — **1 PICK: AFRM ~60/40 → GRADED +10.80% WIN → RECORD 4-for-4**

**RESULT (graded):** AFRM entry 76.85 → **end-AH exit (19:59 ET) 85.15 = +10.80%** (AH peak +12.8%
@86.66; RTH close 77.54). The seasonal read played out: August is AFRM's up-gap quarter (its two
biggest up-gaps ever are both August prints) and it gapped +10.8% AH on the beat. **Record now
4-for-4: ROST +8.46%, OKTA +25.68%, NVDA +4.45%, AFRM +10.80% (avg ~+12.3%).** Honest: n=4 and the one
clean blind call this record ever made (OSIS ~57/43 UP) printed −14.94%; the streak is real but small,
and ~60/40 remains the highest earned lean. The method that is working: washed-out + deep AH book (so
the 19:59 exit is executable) + a base rate SLICED BY QUARTER (the seasonal cut flipped 3 of 5 verdicts
tonight and correctly kept AFRM while passing MRVL, which gave back its NVDA-sympathy gap).

**Timing:** ran 13:28-13:40 ET, not the briefed 15:15-15:50 (same drift as 08-26). Prices are
13:34 ET marks; the user buys near the close, so grade against the actual fill.
**Tape:** SPY 771.79 +0.75%, QQQ +1.19%, VIX 14.49 −4.7%. Risk-ON, with NVDA +9.13% on its beat.

**Field, verified by yfinance timestamps:** AMC 16:00 ET = **ADSK, MRVL, ULTA, GAP, AFRM** — five
names, all tradeable. (DELL/MDB 09-01; LULU/ZS/AMBA/PATH 09-03; NTNX was last night; BURL/DG/RY/TD
are BMO.) No PDUFA dated today, no index add effective tomorrow. Tue/Wed/Thu density confirmed again.

### ⭐ NEW METHOD: cut the base rate by WHICH QUARTER it is — it split the field cleanly

Every prior pass used a flat "last 10 prints" base rate. Tonight four of five names report their
**FY-guide (August) quarter**, and slicing the history by quarter changed three of five verdicts:

| name | px | 20d | off 60d hi | today | AUGUST-quarter gaps | flat last-10 | call |
|---|---|---|---|---|---|---|---|
| **AFRM** | 76.85 | +4.7% | −11.6% | +0.43% | **3up/1down, mean +9.0%** (−12.15/+9.27/+23.84/+15.01) | 7up/3down +4.89 | **PICK ~60/40** |
| ADSK | 269.92 | +14.8% | **−0.7%** | **+5.96%** | 4up/1down, mean +4.48% | 5up/5down +0.95 | **PASS — positioning** |
| MRVL | 244.85 | +33.5% | −25.8% | −0.19% | **2up/4down, mean −1.75%** | 5up/5down +0.44 | PASS |
| ULTA | 530.82 | +2.8% | −6.2% | −2.19% | ex-2020 mean **+0.28%** | 5up/5down +1.59 | PASS ~48/52 |
| GAP | 21.26 | +4.5% | −4.9% | +0.78% | 4up/2down but mean **+1.59%, max ±4.7%** | 7up/3down +3.40 | PASS ~52/48 |

**AFRM ~60/40 lean UP — the only name where the evidence converges.** Its FY-guide quarter is the
quarter it gaps on: **the two largest up-gaps in company history are both August prints** (+23.84
in 2024, +15.01 in 2025), the lone August down-gap being 2022's rate shock that was destroying the
whole BNPL complex. Last **four** prints all gapped up (+15.01/+5.99/+2.11/+1.48). Positioning sits
in the exact zone its up-gaps come from — a run-up-vs-gap table shows the big ones at a *modest*
run-up 10-20% off the high (2024-08: +11.6% run-up, −19.5% off hi → **+23.84**; 2023-11: +8.1%,
−15.1% → +14.75; 2025-02: +0.8%, −15.8% → +13.20); today it is +4.7% / −11.6%, **flat on the day**
= nothing pre-positioned to unwind. Bar: rev ~$1.08-1.11B, EPS $0.35, GMV guide $13.15-13.45B;
Affirm Card volume already disclosed **+146% YoY to $2.13B**, 4.4M active users; Strong Buy, avg PT
**$93.41 vs $76.85**. And the **exit fits the name specifically** — its last two prints gapped UP
then faded the full day (+2.11 → −4.02; +1.48 → −4.97), so a 19:59 sell harvests the gap and skips
the fade. AH book executable: 200-380k sh trade AH on *normal* days, printing to ~19:59.
**Wrong if:** credit — a delinquency/loss-rate uptick or soft FY27 take-rate guide on the 17:00
call sells it through a good quarter (own history: −15.42/−14.67/−12.15); **gap decay is real**
(last two up-gaps only +2.11/+1.48, so a beat may pay ~nothing); $207M/day spread costs something.

**ADSK is the sharpest PASS this record has made, and it required overriding a good seasonal.**
Its August quarter is genuinely strong (4up/1down, mean +4.48%, last four +9.46/+5.45/+4.56/+10.23)
— but its own **positioning** record beats its seasonal. ADSK entering a print with a ≥+6% 20d
run-up AND within ~3% of its 60d high has produced **−7.32 / −7.54 / +4.56 / −7.79 / 0.00 =
1up/3down/1flat, mean −3.62%**, while every big August up-gap came when it was *not* extended
(2025-08: run-up −4.8%, −9.7% off high → **+10.23%**). Today is the most extreme version of the bad
configuration it has ever had: **+14.8% 20d, −0.7% off the 60d high, and +5.96% ON THE DAY of its
own print** (gapped +2.66%, ran another +3.22%). Buying that is paying for the reaction in advance.

**MRVL — three kills, one of them the tell of the day.** August is its *worst* quarter
(2up/4down, mean −1.75%). Its bull case is real (consensus $0.93 sits exactly at the guide
midpoint, beat 5 of 6, 38 Buys / 0 Sells, Polymarket 88% beat). But on **the single best possible
sympathy session for AI silicon — NVDA beat and is +9.13% — MRVL gapped +3.35% and gave the entire
thing back**, closing the read at −0.19% (−3.43% from its open). It could not hold a gift. Layer on
+33.5% in 20d (a 49% rebound off the lows) into a print whose own preview says "Q3 guidance may
determine whether the recovery sustains" = needs-a-perfect-print, carrying the field's fattest left
tail (−17.82, −16.44).

**ULTA was the ROST archetype and it still failed.** Not extended (−6.2% off its 20d/60d high),
consensus $6.20/$2.97B called "achievable" by Oppenheimer, trailing 4-quarter surprise ~10% — the
same washed-out-habitual-beater costume that won this record its first trade. It dies on the
quarter cut: ULTA's August is its **quietest and now negative** (ex-2020 mean +0.28%; last two
Augusts −6.39 and −0.71), its big gaps live in Dec/Mar/May, its last four prints are −0.71 /
+8.43 (holiday) / −9.35 / −3.26, and it is −2.19% today = being sold into the print. Second time
this record has caught "same costume, different setup" (after DKS/ROST).

**GAP dies on MAGNITUDE, not direction.** Best headline base rate in the field (7up/3down, mean
+3.40%, median +7.14%) and a real tailwind (~$80M net tariff relief landing mainly Q2/Q3; FY EPS
$2.30-2.40 RAISED at Q1). But its six August prints are 0.00/+4.17/+4.70/+1.05/−2.37/+1.98 —
mean **+1.59%, none bigger than ±4.7%** — with a mechanical reason: **August is a mid-cycle quarter
with no holiday guide, and GAP's ±15-20% gaps all come off the Nov/Mar holiday reads.** A gap is
what I harvest; this quarter structurally doesn't produce one big enough to pay a $21 stock's AH
spread on $118M/day. Plus its last two prints crashed −11.36% and −14.60% (a 2026 regime change the
2024-era seasonal may not survive) and it is +8.4% in 5d into the print.

**Honest frame.** One pick, not three — ULTA or GAP would have been slot-filling, the error flagged
on VEEV. ~60/40 is the highest lean this record has stated and it is earned by name-specific
evidence (right quarter + right positioning + up-streak + an exit that matches the name's own
gap-then-fade pattern), not by three straight wins. Against that: n=3, two on one night, and the
one clean blind call ever made here (OSIS ~57/43 UP) printed −14.94%. Nothing sized up.

Plan: `overnight/plans/2026-08-27.txt`. **1 `journal.log` call** (AFRM 76.85; ah_mark empty —
`grade()` fills it from tonight's ~19:59 ET mark). Nothing written to resonance / exec_ai / swing.

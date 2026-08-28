# runner — forward record (OFF-RECORD, separate from all trading systems)

**What this is:** a ~10:30-ET confirm scan for penny / small-cap TOP GAINERS, predicting which CLOSE up
>+10% on the day. The edge (backtest-seeded): a penny gainer's direction is a coin flip at the 09:30
open but has resolved + persists by ~10:15-10:30 (83% on n≈12), so runner reads the *confirmed* movers,
filters by who-buys (flow arriving vs consumed), and calls the >+10% closers.

**Isolation (hard):** lives ONLY here + `data/runner.db`. NEVER written to resonance/overnight/exec_ai/
swing/rotation. It forecasts/experiments; it does not trade.

**Honest prior:** penny top-gainers are pump-and-dump prone; 83% persistence is n≈12, high variance,
selection-biased. Every call carries honest odds and is graded forward at the close. Nothing sized until
the >+10%-close calls beat chance over a real forward sample.

---

## 2026-08-27 — FIRST 2 WINS (momentum+gate+offense thesis), but BRNX −53% reopens the exit

First day the rebuilt thesis (momentum POND + blow-off gate + higher-highs offense, hold-to-close) got
hits. Graded, hold-to-close:

| pick | scan | entry | peak | HOLD-TO-CLOSE | (trail-15% ref) |
|---|---|---|---|---|---|
| **USDE** | 10:30 | 7.28 | +16.8% | **+12.2% HIT** ✅ | +12.2% |
| **CELU** | 10:50 | 1.849 | +37.9% | **+12.4% HIT** ✅ | +17.2% |
| USDE | 10:50 | 7.74 | +9.8% | +5.5% | +5.5% |
| USDE | 11:06 | 8.33 | +2.1% | −1.9% | −1.9% |
| USDE | 12:29 | 8.17 | +3.4% | −0.0% | −0.0% |
| **BRNX** | 11:38 | 8.18 | +26.6% | **−53.0%** 🔴 | +7.7% |
| WRAP | 12:29 | 1.795 | +0.3% | −4.5% | −4.5% |
| JFB | 12:38 | 4.79 | +0.7% | −1.5% | −1.5% |
| DFDV | 11:38 | 5.376 | +2.5% | −2.2% | −2.2% (catalyst-name control) |

**Scoreboard now 2/17 = 12%, avg hold-to-close −4.86%.** The two hits (USDE/CELU) are the EARLY window
(10:30/10:50) — the later legs all missed and BRNX imploded. "Enter early" is now strongly confirmed
intraday: the morning picks won, the afternoon picks (11:38+) missed or crashed.

**⚠️ BRNX reopens the exit question.** BRNX peaked +26.6% then closed **−53.0%** on hold-to-close, but a
15% trailing stop would have exited it at **+7.7%**. Across all graded picks the trail-15% reference
(−1.83% avg) now BEATS hold-to-close (−4.86% avg) — driven entirely by BRNX. Trailing was removed 08-25
because it gave back PRZO's peak; but a blow-off that ROUND-TRIPS to −53% is exactly what a trail exists
to catch. The honest read: hold-to-close is fine for a grinder that holds, dangerous for a blow-off that
craters. This is n=1 for the −53% case, but it's a large single loss the exit could have avoided.
Candidate revision to test forward: a WIDE trailing stop (or a hard SL) as a crash-floor while keeping
hold-to-close for the grind — NOT the tight 15% that clipped PRZO. Do not act on n=1; track whether
blow-off-picks keep round-tripping.

**Structural window finding (the AI stated it):** the thesis is calibrated on a 10:30 entry with ~5.5h
to grind to +10%. Afternoon re-runs (11:38, 12:29, 12:38, 12:55) structurally offered only spent
squeezes or slow grinders and produced misses/crash/abstain — "if late re-runs keep abstaining, that's
the window telling you something, not the field." Run the standard 10:30 window; do not chase re-runs.

**Prescreen validated:** the 3-4× speedup (mechanical board+metrics in ~30s) held up, and the AI still
OVERRODE the mechanical flags where its judgment differed — it picked CELU (which the raw blow-off gate
would have blocked) and caught a prescreen halt-field bug (HSDT). Judgment stayed with the AI.

## Open finding — the catalyst filter has dropped the day's biggest winner 2 days running

The thesis SELECTS on a fresh catalyst + not-extended entry and DROPS no-catalyst momentum. Two straight
live days, the single biggest mover on the board was a no-catalyst name the filter dropped:
- **08-24:** dropped **PMI** (faded −2.2% at 10:30 → +17.5%); the up-confirmed momentum names it would
  have bought under the OLD thesis crashed (BTCT +55% → −32%). This is what forced the catalyst revision.
- **08-25 [hindsight, late-fire replay]:** dropped **NCPL +111% peak / trail +10.0% HIT** and **PMI +47%
  peak / trail +25.0% HIT** — both verified no fresh catalyst (PMI last item Q2 08-19, NCPL last PR 08-12,
  a float-squeeze/consolidation bucket). Both were also *extended* at 10:30 → fail both filters.

**NOT rewriting the thesis on this.** The same no-catalyst bucket also held every big LOSER on the 08-25
board (AIXI −8.3%, TNMG −11.3%, BTCT −11.9%, OFAL −8.0%, DAIC −2.2%). It is the high-variance bucket the
filter was built to avoid paying for. The open question — is avoiding it worth the winners it costs? — is
settled by the forward record, not another same-day post-hoc revision. Watch whether the dropped winners
keep beating the picked catalyst names over a real sample.

**Window note:** a 10:20 window was tried + reverted 08-25 (noise: +0.55% on n=3, worse on PRZO). Entry
stays modeled at the 10:30 bar. scan.sh now flags a late fire so a post-10:30 lookup can't be logged as a
forecast.

## 08-26 REPLAY of the FIXED thesis (both filters) — turns the losing day into avoid-all-losers

Applying DEFENSE (blow-off gate) + OFFENSE (higher-highs into 10:30) to the whole 08-26 board (hindsight,
≤10:30 select): it BLOCKED the crashers (CRE −18.2%, XPON −15.9%) and REJECTED every fader as spent
(CAPR −4.5%, LBGJ −8.3%, LUCY −3.4%, DAIC −0.6% — all had HOD early + no new highs into 10:30). Exactly
ONE name passed both filters: **QBTZ @ $3.62** (blow-off −3.1% ok; HOD 10:28, higher-highs +4.7% into the
entry) → closed **+2.5%** (green, not a +10% hit but not a loss). QBTZ is a leveraged/inverse ETF, and per
the decision 08-26 an ETF is a VALID momentum vehicle (the thesis is momentum+shape, not a company story)
— so it is a legitimate pick, not the old "not a stock" drop. Net: the fixed thesis on 08-26 = one green
pick (+2.5%) and it AVOIDED every loser the old catalyst thesis would have taken (it picked CAPR −4.5%).
The fix converts a losing replay into a no-loss day. Still in-sample; forward-test.

## 08-26 FIX — added the OFFENSE signal (still-making-higher-highs); blow-off gate alone wasn't enough

Replaying the momentum+gate thesis on 08-26 (hindsight, ≤10:30 select) still LOST: the gate correctly
BLOCKED CRE (−15.4%) and XPON (halt, −16.1%) — the two worst — but every PASS name lost too (best was
LBGJ, top-momentum, closed −8.7%). A losing replay means the system needs a fix, so diagnosed what
separates the 08-25 winners from the pass-but-lose names:

| name | @10:30 vs HOD | HOD printed | higher-highs into 10:30 | close |
|---|---|---|---|---|
| NCPL (win) | −0.7% | **10:30** | **+28.4%** | +51.1 |
| JEM (win)  | −0.9% | **10:30** | +1.6% | +21.1 |
| PMI (win)  | −10.2% | 10:27 | +23.6% | +14.6 |
| PMI (win)  | −4.3% | 10:06 | +2.3% | +16.3 |
| LBGJ (lose)| −1.4% | 09:52 | −1.4% | −9.2 |
| CAPR (lose)| −3.6% | 10:10 | +5.1% | −4.1 |
| LUCY (lose)| −5.2% | 09:48 | −3.2% | −3.0 |
| DAIC (lose)| −23.3% | **09:30** | −16.7% | −2.8 |

**The signal: is momentum STILL BUILDING into the entry?** Winners were stamping new highs right into
10:30 (HOD at/near 10:30, higher-highs positive); losers had printed their HOD early (09:30-10:00) and
made no new high into 10:30 — the recurring "HOD is behind the entry" killer. Adding an OFFENSE filter
(HOD recent + higher-highs into the entry) keeps all 4 winners and drops 3 of 4 pass-losers (CAPR the lone
false-pass, a day-3 consumed catalyst). It also gives the ABSTAIN discipline the system lacked: on 08-26
NO name was making new highs into 10:30 (LBGJ peaked 09:52, DAIC 09:30, LUCY 09:48) → the correct output
is ABSTAIN, not a forced LBGJ pick. So the thesis is now DEFENSE (blow-off gate) + OFFENSE (higher-highs
into entry) + hold-to-close, abstain when the field is spent. Still in-sample — forward-test.

## 08-26 RETROSPECTIVE — the fresh-catalyst thesis was BACKWARDS; pivoted to momentum + blow-off gate

Graded every PICK and every DROP across 08-24..08-26 from a 10:30 entry, hold-to-close. The dropped
no-catalyst squeezes beat the catalyst picks decisively:

| name | date | pick/drop | catalyst | blow-off (1-bar) | close% | hit +10%? |
|---|---|---|---|---|---|---|
| NCPL | 08-25 | DROP | none (Wells notice) | −10.4% | **+51.1** | ✓✓✓ |
| JEM  | 08-25 | DROP | none (consolidation) | −8.3% | **+21.1** | ✓ |
| PMI  | 08-24 | DROP | none (float squeeze) | −8.0% | **+16.3** | ✓ |
| PMI  | 08-25 | DROP | none | −10.9% | **+14.6** | ✓ |
| LUCY | 08-24 | DROP | none | −13.7% | +13.0 | ✓ (false block) |
| BTCT | 08-24 | DROP | none (momentum) | **−16.0** | −28.0 | ✗ crasher |
| CRE  | 08-26 | DROP | fresh PR | **−17.7** | −8.8 | ✗ blow-off |
| PRZO | 08-25 | PICK | federal order | −6.3% | +3.3 | ✗ |
| GRML | 08-25 | PICK | rare-earth NPV | −8.7% | −12.1 | ✗ |
| RZLV | 08-25 | PICK | Google deal | −5.0% | −0.3 | ✗ |
| CAPR | 08-26 | PICK | day-3 re-rate | −4.3% | −4.4 | ✗ |

**Dropped bucket: +6.9% avg, 4-of-8 hit +10%. Catalyst picks: −0.3% avg, ~1-of-5.** The fresh-catalyst
filter was systematically selecting AGAINST the winners: a catalyst that already re-rated has no
follow-through, while the no-catalyst momentum squeezes grind up all day and HOLD to close.

**What separates winner from crasher = the BLOW-OFF (first-hour single-bar high→low drop):** every
crasher > ~−16% (BTCT −16.0→−28; CRE −17.7→−8.8), every winner < ~−11% (PMI/NCPL/JEM −8 to −11). A
~−13% gate splits them. Consistency check on all 14 obs: PASS bucket +7.2% avg vs BLOCK bucket −8.3%.

**Honest limits of the gate (do not over-claim):** (1) IN-SAMPLE, n=14, one metric, and the PASS average
is heavily carried by NCPL +51 (ex-NCPL the PASS bucket is +2.8%). (2) It mislabelled **LUCY** — a −13.7%
blow-off that still closed +13% — so a blown-off name can RECLAIM and win; the gate is a crash-avoider,
not a winner-picker (PASS bucket is still only ~1/3 winners). (3) The "volume-persistence" sub-signal
(2nd-half vs 1st-half volume) did NOT separate winners from chop (CAPR/XPON high volTrend but lost; JEM
low but won) — dropped it. Forward-test before trusting.

**Entry-timing / "when does it come back":** the LUCY case is why a blocked (blown-off) name is watched,
not booked dead — it earns back in only by RECLAIMING (higher lows re-forming, volume returning with
price, the reclaim HELD, not a one-bar dead-cat bounce). Clean grinders are the straightforward ~10:30
buy; blown-off names are candidates again only on a convincing held reclaim before the entry window.

**Premarket / overnight visibility (checked 08-26):** the winners ARE visible pre-open (they gap +3.6 to
+41%), so the pond can be built off the premarket gainers board — but the gap ALONE does not separate
winner from crasher (BTCT +43.9% ≈ PMI +41.1%; only an extreme gap like CRE +137% is a tell). The
crash-gate NEEDS the RTH first hour (the blow-off is intraday price action). Overnight is the WRONG tool —
these are float-squeeze momentum, not earnings gaps, so the earnings-based overnight system can't see them.

## 08-25 GRADED — 0/5 hit, but the loss was the EXIT, not selection → trailing removed

Final grades (yfinance, 15:55 RTH close, prices verified against an independent re-pull; GRML's 1-for-50
reverse split was 08-24 so all 08-25 bars are one post-split basis — no artifact):

| pick | window | entry | peak | hold-to-close | (trail-15% ref) | day (free ref) |
|---|---|---|---|---|---|---|
| PRZO | 10:30 | 0.7793 | **+15.5%** | **+3.3%** 🟢 | −1.8% | +28.6% |
| PRZO | 12:13 | 0.8098 | +11.1% | −0.6% | −5.5% | +28.6% |
| GRML | 10:30 | 10.98 | +4.7% | −12.1% | −11.0% | +12.9% |
| GRML | 12:13 | 10.53 | +2.9% | −8.4% | −12.5% | +12.9% |
| RZLV | 10:30 | 2.935 | +5.3% | −0.3% | −11.0% | +20.4% |

**The exit was the loss driver, not the pick.** Every name peaked green (PRZO +15.5%), but the 15% trail
gave it all back (PRZO exit −1.8%). Across all 7 graded picks hold-to-close (−6.84% avg) beats the trail
(−8.84% avg). **Trailing REMOVED 08-25; exit is now hold-to-close** (matches resonance's buy→hold-EOD).
hit = trade_pct ≥ +10%. Accepted trade-off: hold-to-close gives back an intraday spike (08-24 DAIC +42%
peak faded) → entry-not-extended now carries more weight to avoid round-trips.

**Selection was RIGHT — context picked the winner.** PRZO (best context: federal-contract = recurring
buyer, entry 55% of range = room, liquidity 562k/5min vs GRML 54k) had the highest peak AND was the only
green close. GRML lost on one-shot-catalyst + dead liquidity; RZLV was extended (98% of range) at entry.

**A/B (early vs late entry), on peak:** PRZO 10:30 +15.5% > 12:13 +11.1%; GRML 10:30 +4.7% > 12:13 +2.9%.
Early (10:30) offered the bigger peak both times — the day's high was already behind the 12:13 entry. n=3,
one direction, one day — not proof, but consistent with "enter early."

**Knowable-at-10:30 finding (not hindsight):** at 10:30 the data DID separate the three — RZLV extended
(98% range), GRML thin (54k vs PRZO 562k/5min) + one-shot catalyst. The brain ranked PRZO #1 but only 30
vs GRML 28 — it under-weighted liquidity + recurring-buyer, both visible at 10:30. Only the "second demand
push" (PRZO 11:20–29) was true hindsight. Candidate decide tweak (track first): weight early-liquidity +
recurring-buyer catalyst harder. NOT yet applied — n=1.

## Record
_(one line per graded pick: called at 10:30 -> closed -> hit >+10%? via HOLD-TO-CLOSE)_

**08-25:** PRZO 10:30 +3.3% miss · PRZO 12:13 −0.6% miss · GRML 10:30 −12.1% miss · GRML 12:13 −8.4% miss
· RZLV 10:30 −0.3% miss. **0/5 hit.** Running: 0/7, avg hold-to-close −6.84%. Thesis UNPROVEN, n small.
Controls (no-catalyst, not bought): NCPL peak +169%→crashed, PMI +25%→faded, JEM +8.68 HOD→6.22 — big
peaks, all round-tripped (the pump-dump the filter avoids); open question whether avoiding them nets out.

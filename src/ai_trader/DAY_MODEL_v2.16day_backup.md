# How a Trading Day Works — v2 mental model (learned from the tape)

Built by studying ~16 past days end-to-end (SITUATION → NEWS → WINNERS → ACTION)
across every 2026 regime. This is the "how a day works" model the v2 brain should
carry into the pre-open judgment. It is **descriptive of what actually closed up**,
not a formula. Days cited are real; go re-read them with `day_story.sh <date>`.

Sample studied: 01-20, 01-21, 03-06, 03-30, 03-31, 04-08, 04-17, 05-06, 05-28,
06-05, 06-24, 06-30, 07-10, 07-13, 07-16, 07-17 (2026).

---

## 0. The one number that matters most (quantified edge)

Across the 13 non-crisis days studied, I bucketed every liquid name by its state at
09:35 (5-min close vs the 09:30 open) and measured hold-to-close return:

| 09:35 state           | n     | avg fwd-to-close | % that closed ≥3% |
|-----------------------|-------|------------------|-------------------|
| **down >1% from open**| 1383  | **+0.77%**       | **18.6%**         |
| −1..0%                | 3883  | +0.35%           | 8.1%              |
| 0..+1%                | 4160  | +0.21%           | 6.0%              |
| +1..+2%               | 1235  | +0.09%           | 8.8%              |
| **already up >2%**    | 458   | **−0.02%**       | 13.8% (bimodal)   |

**The day's winners look flat-to-RED at 09:35, not already-up.** The names down from
the open are the single best pool; the names already up >2% have *negative* average
forward return (you are the exit liquidity for the early chaser). The winner's edge
is the **reclaim**, not the early lead. `gain_at_0935 ≈ 0 or slightly negative` is
the signature on essentially every winner across every day (LCID, MU, QCOM, DELL,
AMBA, HIMS, the whole semicap complex — all opened flat/red then ran).

**BUT this edge is 100% regime-conditional.** On the 3 crisis/bleed days (03-06,
03-30, 06-05) the exact same bucket **inverts**:

| 09:35 state (crisis days) | n   | avg fwd | % win3 |
|---------------------------|-----|---------|--------|
| down >1% from open        | 349 | **−3.61%** | 0.9% |
| flat/up                   | ~1850 | −0.7 to −1.2% | ~1.4% |

Same "buy the dip" signature = the day's **best trade** on a healthy tape, a
**falling knife** on a fear tape. **Everything downstream depends on reading which
regime you're in first.** That read is the whole job.

---

## 1. Read the regime FIRST (this gates everything)

Inputs: VIX level + 1-day change, SPY regime, breadth (ad_ratio, pct_above_20d,
new_highs/lows), and — critically — **is the whole tape red or just one group?**

| Regime | Tell | Reclaim edge? | Play |
|---|---|---|---|
| **Calm bull / grind** | VIX <17, SPY up, breadth ok | YES | beaten high-beta reclaim + real gap-ups |
| **Broad up / bounce** | SPY +1%+, breadth surge | YES, strongest | buy the beaten leaders early — visible by 10:00 |
| **Rotation (flat SPY)** | sectors split, VIX mid | YES but narrow | the reclaim cluster ≠ the green sector (see §4) |
| **VIX-pop washout** | VIX teens→~19-20, ONE group hit, **rest of tape green** | YES (waits) | buy the beaten group's reclaim, confirm by 11:00 |
| **SKIP / bleed** | VIX spikes >~21, **whole tape red**, breadth collapses, SKIP regime | **NO — inverts** | abstain or defensives only |
| **Deep crisis** | VIX 25-30+ sustained, pct_above_20d <35% | NO | flat, or low-beta/insurance/gold/defense |

The washout-vs-bleed distinction is the hardest and most valuable call:
- **07-17** — chips gapped down (XLK −1.1%) but Consumer Cyclical/Industrials were
  GREEN (+2%). Only chips were hit → the whole semicap complex reclaimed +7-11%.
  **Buyable washout.**
- **06-05** — chips also sold off, but the WHOLE tape was −2.6%, VIX 15→21.5, XLK
  −6.66%. Epicenter WAS the high-beta group itself → no reclaim, winners were purely
  defensive (VXX, KMB, staples, REITs). **Un-buyable bleed.**
- Rule of thumb: **high-beta reclaims when it's collateral damage in a macro wobble;
  it keeps bleeding when it's the epicenter of the selloff.** And: if the rest of the
  market is green under the beaten group, buy it; if everything is red, don't.

---

## 2. The winning ACTION signature (what a real bid group looks like early)

Winners almost never gap up and hold from a lead. The dominant shape is
**gap-down/flat-open → reclaim**. Read it via reclaim COUNT, not sector average:

- **Reclaim COUNT is the signal, not avg_gain_now.** The sector average is dragged
  down by mega-cap index names; the *number of names going red→green* is what marks
  the real bid. On the clean bounce/momentum days the winning group's reclaim count
  is unmistakable: 03-31 Tech 33→46 reclaiming by 10:00, 06-30 Tech 24→43, 07-17
  Tech 31→53. That IS the day's trade, visible in real time.
- **Broad move = visible at 10:00. Narrow cluster = invisible until ~11:00+.** When
  the winning group leads the whole sector (03-31, 06-30, 07-17), you see it at 10:00.
  When it's a *sub-industry inside a flat/red sector* (semis inside a red "Technology"
  on 06-24 and 07-10 — MU +15, QCOM +13 while the Tech aggregate was −0.9% all day),
  the aggregate HIDES it and the `names` view still shows them red at 10:00 because
  they reclaim to green only after 10:00. On those days you must recognize the SETUP
  (beaten cluster, high rv, gapping down but stabilizing at the open) rather than wait
  for confirmation.
- **On a bleed day there is no reclaim to see** — action is red everywhere, ~1
  reclaiming (06-05, 03-06). That absence is itself the signal to abstain.

---

## 3. SITUATION + NEWS → which WINNERS (recurring maps)

- **Semiconductors / semicap are the recurring high-beta winner cluster.** They show
  up as the day's biggest winners on washout days (01-20, 07-17), calm days (07-10),
  rotation days (06-24), and bounces (03-31, 06-30) — the whole complex moves as one
  (MU/WDC/STX/AMAT/KLAC/LRCX/TER/ONTO/COHR/AMKR/ARM/CRDO...). If any group is going to
  reclaim on a healthy-ish tape, it's usually this one.
- **A one-group scare with a healthy tape is the bread-and-butter setup.** Pre-open
  news names the beaten group ("Nasdaq tumbles on chip selloff" → 07-17). If the rest
  of the tape is fine, that group is the buy.
- **Energy IS a clean trade — but only when crude gaps.** On 07-13 crude gapped +9%
  overnight → oil/refiners (UCO, CVI, NOG, PARR) gapped up and held; foreseeable
  pre-open, visible in the 09:45 energy action. But it's a **narrow, modest gap-and-
  hold (+3-8%), not a big runner**, and the higher-beta refiners/E&P move far more
  than XLE/XOM (last-mile linkage). Conversely, when crude **crashes** after being
  extended (04-08: −16%; 04-17), the beaten energy/materials names gap down 10-16%
  and **reclaim** — XLE-the-ETF closed red both days while the individual names were
  the biggest winners.
- **The "loud" story is usually NOT the trade.** On the Iran-war/oil-shock days
  (03-06, 03-30) energy the sector was muted (+0.16%) and the winners were defensive/
  idiosyncratic (HIMS +40, insurance, utilities, gold, a little defense). The headline
  that everyone is talking about is already priced; the trade is the mechanical
  reaction elsewhere.
- **Earnings gap-ups run, and drag their cluster.** DELL +38% on earnings pulled the
  whole AI-server group (HPE/SMCI/NTAP) up with it (05-28); AMBA earnings +31 (06-30);
  BLMN/DVA/MRVL/AVAV/KTOS on their days. Genuine catalyst gap-ups (gap strongly +) are
  the second winner archetype alongside reclaims. Sympathy peers of a big earnings
  mover are a real, tradeable follow-on.
- **Bounce day = buy yesterday's washout.** 01-20 washout → 01-21 snapback (breadth
  ad_ratio 0.25→4.2): the exact names crushed on D-1 (semis, EV, beaten mega-caps) led
  D+1, all opening flat and grinding. The D-1 oversold-snapback names the day's bid
  group. Same 03-30 capitulation → 03-31 V-bounce (Tech +4.2%).

---

## 4. What's FORESEEABLE vs not

**Foreseeable pre-open (plan it):**
- **Crude gapped overnight** → energy gap-and-hold (long) or, if crude crashed off an
  extended level, energy/materials reclaim. Directly from the macro/crude tape.
- **A single group gapped down on a scare while futures/breadth are otherwise fine** →
  that group's reclaim (07-17 chips). Read from pre-open news + which group is hit.
- **D-1 was a VIX-pop washout that closed off its lows / capitulation** → next-day
  snapback in the beaten high-beta (01-21, 03-31). Read from D-1 tape + oversold breadth.
- **A big earnings gap-up** and its sympathy cluster (05-28 DELL, 06-30 AMBA).

**Foreseeable by ~10:00-11:00 (confirm intraday):**
- Broad bounce/momentum days: the leading group + rising reclaim count is visible by
  10:00 (03-31, 06-30, 07-17). Safe to lean in once the reclaim count is climbing.

**NOT reliably foreseeable / avoid:**
- **Which flat-tape day the narrow semi cluster reclaims** — invisible at the sector
  level and still red at 10:00 (06-24, 07-10). Only the *setup* (beaten, high rv,
  stabilizing) is knowable; the confirmation comes late.
- **Idiosyncratic monster movers** (HIMS +40 on 03-06) — single-name news, not a pattern.
- **Whether a fresh VIX spike washes out and reclaims or keeps bleeding** — if the
  whole tape is red with breadth collapsing (06-05), do not pre-commit to the dip;
  either the SKIP gate fires or you wait for the reclaim count to actually build.

---

## 5. Operating rules for the v2 brain (distilled)

1. **Regime read is the whole game.** Decide washout-reclaim vs bleed BEFORE picking
   names. Wrong regime → the same pick is +0.77% or −3.6%.
2. **Don't chase the 09:35 leader.** Prefer names flat/red from the open with high
   early rv on a healthy tape — that's the reclaim pool (`gap_down_reversal`,
   `oversold_bounce`). Already-up-2% names fade on average.
3. **Count reclaims, don't read sector averages.** A rising red→green count in a group
   is a live bid; a flat sector average can hide the day's best cluster.
4. **Semis are the default high-beta reclaim vehicle**; when they're beaten on an
   otherwise-fine tape, they're usually the trade — even when "Technology" looks red.
5. **Energy only when crude moves** — gap-and-hold on a crude gap-up (modest, narrow),
   or reclaim on a crude crash-off-extended. Favor high-beta refiners/E&P over XOM/XLE.
6. **The loud headline is usually priced.** Trade the mechanical reaction, not the story.
7. **On bleed/crisis (VIX spike + whole-tape-red + breadth collapse): abstain or go
   low-beta defensive.** Buying red-at-open here is a falling knife (0.9% win rate).
8. **Earnings gap-ups and their sympathy cluster** are the clean long archetype on
   healthy tapes (`earnings_gap_and_go`, `news_catalyst`).

See also memory: `ai-trader-last-mile-rule` (buy the mechanically-linked high-beta,
not the ETF), `ai-trader-daily-bid-group` (name the day's rotation via D-1 snapback).

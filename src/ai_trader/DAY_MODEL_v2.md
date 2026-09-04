# How a Trading Day Works — v2 mental model (SCALE-VALIDATED)

Rebuilt after testing the 16-day model against **1,433 trading days** (Oct-2020 →
Jul-2026), **517,359 liquid symbol-days** (dvol ≥ $50M), 5-min bars in
`intraday_bars_5m`. Every claim below is either backed by that sample or explicitly
killed. The original 16-day writeup is preserved in `DAY_MODEL_v2.16day_backup.md`.

**Definitions used throughout.** For each name/day: `open` = 09:30 bar open,
`p0935` = 09:30 bar close (price at 09:35), `close` = **15:55 bar close** (last
regular-session bar — NOT the after-hours bar the `winners` helper reads).
`g0935 = p0935/open − 1`. `fwd = close/p0935 − 1` (hold from 09:35 to the bell).
Forward returns winsorized to [−50%, +100%]; "field" = avg `fwd` over all liquid names.

---

## 0. TL;DR — the honest bottom line

**The 16-day model's central thesis inverted at scale.** It said: *the day's winners
open flat/red, buy the reclaim pool, the already-up names are exit liquidity that
fades.* At 1,433-day scale the opposite is true and robust:

- **The already-up-2% pool is the best pool, not the worst — every year.** It beats
  the field by **+0.21% to +0.62%/yr** (avg ≈ +0.4%), positive in all 7 calendar
  years. This is early intraday momentum / relative-strength continuation, knowable at
  09:35. The 16-day "up>2 = −0.02%, you're the exit liquidity" was noise.
- **The red-reclaim pool barely beats the field: ≈ +0.04%/yr, and it was *negative*
  in 2022.** The single "+0.77% red vs +0.35% field" table that the whole v2 model was
  built on does **not** replicate. Unconditionally the red-pool edge over field is
  +0.06% (t≈4.7 — statistically nonzero, economically nothing, gone after costs).
- **The spectacular "regime-conditional edge" (+0.8% bull / −0.67% bear) was a
  look-ahead artifact.** `spy_regime` and same-day `vix_close` are *same-day-close*
  labels: BULL days average +0.51% intraday tape return, BEAR days −0.55%, but their
  *opens are identical* (+0.016 vs −0.012). Conditioning the forward return on them is
  circular ("names that opened red rose on days the market rose"). Not tradeable.
- **What genuinely survives as a causal edge:** (a) the **up>2 momentum** tilt above,
  and (b) an **oversold snapback** — buying the red pool the day *after* a down day —
  but (b) is year-dependent (works 2021/22/25, fails 2023/24) and is *still* beaten by
  the up>2 pool even on those days.

**Is there a real, regime-conditional edge you'd trade? A small one: the up>2
early-momentum tilt (~+0.3–0.4%/yr over field, positive every year).** But it's thin
(win rate 50.9%, median only +0.07%, mean carried by the right tail), so it's a
harvest-the-tail-across-many-names play, not a per-trade money-maker. Everything the
v2 model actually *emphasized* — the red reclaim, the regime inversion — is at scale
**~zero or an artifact.** Trade the momentum tail with discipline; don't trust the
reclaim story.

---

## 1. The one number, at scale (this replaces the old §0)

Liquid universe (dvol ≥ $50M), all 1,433 days, bucketed by `g0935`:

| 09:35 state | n | avg fwd | median fwd | win% | %≥+3% | t-stat |
|---|---|---|---|---|---|---|
| red < −1% | 33,370 | +0.088% | +0.094% | 51.4 | 12.9 | 4.7 |
| −1..0% | 213,609 | +0.011% | +0.023% | 50.6 | 4.1 | 2.7 |
| 0..+1% | 237,268 | +0.006% | +0.000% | 49.7 | 4.1 | 1.6 |
| +1..+2% | 25,716 | +0.153% | +0.024% | 50.3 | 11.4 | 8.2 |
| **up > +2%** | **7,396** | **+0.472%** | **+0.105%** | 51.2 | 22.3 | 8.2 |
| FIELD | 517,359 | +0.028% | — | 50.2 | — | — |

Read it right: forward return is a **J-shaped function of the morning move's
magnitude** — both tails beat the flat middle, and the **up-tail is highest**. This is
a volatility/beta selection effect (extreme-morning-move names carry high forward
variance) with a **momentum tilt** (up-tail > down-tail). The red pool's median
(+0.094%) ≈ the up-pool's median (+0.105%); the up-pool wins on the **mean** because
its right tail is fatter (continuation monsters / earnings gap-and-go, p90 = +5.8%).

**Momentum dominates reclaim in every cut.** red<−1 minus up>2 is negative in every
regime (−0.31 in up-tapes, −0.36 in down-tapes). There is no slice where buying the
red pool beats buying the up pool.

---

## 2. Regime conditioning — mostly a look-ahead mirage (the key correction)

The 16-day model's headline was "the same pick is +0.77% or −3.6% depending on
regime; the regime read is the whole game." At scale, the strong version of that is an
artifact of **look-ahead labels**:

- `spy_regime` (BULL/BEAR) is assigned from the day's own close. BULL days = +0.51%
  avg intraday tape move, BEAR = −0.55%, **identical opens**. It flips ~45% of days
  (BULL→BEAR 343 vs BULL→BULL 413), so it isn't even a persistent "regime" — it's a
  same-day up/down tag. Conditioning on it is circular.
- Same-day `vix_close` is the day's *closing* VIX, which rises precisely when the tape
  falls. The clean monotonic "edge best at VIX 16-25, inverts >30" table is largely
  the same circularity.

**When you re-condition on only *pre-open-knowable* info, the edge collapses:**

| conditioner (pre-open) | red-pool fwd |
|---|---|
| prior-day VIX < 16 | −0.13% |
| prior-day VIX 16-20 | +0.14% |
| prior-day VIX 20-25 | +0.26% |
| prior-day VIX 25-30 | −0.11% |
| prior-day VIX > 30 | +0.23% |
| prior-day spy_regime = BULL | −0.04% |
| prior-day spy_regime = BEAR | +0.27% |

Non-monotonic, weak, and prior-day regime is a coin flip. **The tradeable regime edge
is far smaller than the 16-day model claimed.** Keep the *instinct* (fear tapes punish
dip-buying) but distrust any big number attached to a same-day macro label.

---

## 3. What DOES survive causally: the oversold snapback

The one clean, pre-open-knowable reclaim signal is **daily mean reversion** — condition
the red pool on the **prior day's tape return** (fully knowable at today's open):

| prior-day tape return | red-pool fwd | win% | %≥+3% |
|---|---|---|---|
| D−1 crashed < −1% | **+0.843%** | 59.5 | 19.4 |
| D−1 down (−1..−0.3%) | +0.066% | 51.5 | 12.2 |
| D−1 flat | +0.089% | 51.6 | 13.0 |
| D−1 up | −0.117% | 48.8 | 10.5 |
| D−1 ripped > +1% | −0.338% | 46.9 | 11.2 |

Monotonic and causal — this **validates the "buy yesterday's washout" claim** (01-20→
01-21 in the old sample) at scale, and reframes the VIX story: **the knife is
*intraday, same crisis day*; the snapback is the *next* day.** Best combined causal
gate: **D−1 down AND prior VIX > 28 → red pool +1.43%, win 65%** (fear already
elevated + a down day behind you = the reversion setup). Cross-sectionally it's real
too: the day after a −1% crash, the red pool (+0.84%) beats the field (+0.32%) by
+0.52% — but the up pool still tops both at +1.92%.

**Two honesty checks keep it from being a slam-dunk:**
1. **It's year-dependent.** Red-pool-after-a-down-day: +0.48% (2021), +0.24% (2022),
   +1.07% (2025) — but **−0.22% in 2023** (inverts) and −0.01% (2024). It works in
   high-volatility mean-reverting years and dies in calm trending ones. That
   regime-dependence is only partly knowable in advance.
2. **Momentum still beats it.** Even the day after a −1% crash, up>2 names return
   +1.92% vs the red pool's +0.84%. The up pool is never not the best pool.

---

## 4. Washout vs bleed — what the discriminator really is

The 16-day model's hardest call (buyable washout vs un-buyable bleed) partly holds,
but the working discriminator is **VIX level + a down day behind you, not
open-breadth**. On **down-open days** (tape mean g0935 < −0.2):

| discriminator | red-pool fwd | win% |
|---|---|---|
| VIX < 18 | +0.52% | 58 |
| VIX 18-22 | +0.39% | 56 |
| VIX 22-28 | +0.18% | 51 |
| **VIX > 28** | **−0.69%** | 43 |

Clean: on a weak-open day, low/moderate VIX → reclaim; **VIX > 28 → knife.** That's a
real *don't-catch-the-knife* gate for the deep end. But the model's "breadth of the
down-move" idea (narrow one-group scare vs broad tape-red) did **not** separate
reclaim from knife cleanly — `pct_red_open` buckets were noisy and reversed. **Use VIX
extremity, not open-breadth, as the bleed gate.** (Caveat: the VIX>28 knife uses
same-day VIX; as a live tell, read the VIX *level at the open* + whether D−1 was
already down — those are causal.)

---

## 5. What was KILLED (did not survive scale)

- ❌ **"Winners open flat/red; the reclaim pool is the day's best pool."** False. The
  red pool ≈ field (+0.04%/yr, negative in 2022). The up>2 pool is best, every year.
- ❌ **"Already-up-2% names fade / you're the exit liquidity."** Inverted. up>2 = the
  robustly positive pool (+0.4%/yr over field).
- ❌ **"Regime conditioning gives a +0.8/−0.67 swing."** Look-ahead artifact of
  same-day labels; the causal version is small and non-monotonic.
- ❌ **"SKIP-regime days = falling knife, 0.9% win."** At scale, days labeled SKIP had
  a *positive* red-pool edge (+0.18); the label ≠ a bleed day. The real knife condition
  is same-day VIX>28 / a sustained down-move, not the SKIP tag.
- ❌ **Open-breadth as the washout/bleed discriminator.** Noisy, didn't separate.
- ⚠️ **"Count reclaims by 10:00/11:00."** Not tested here (needs an intraday 10:00
  snapshot); untrusted until validated the same way. The v2 emphasis on watching a
  reclaim count build is plausible but unproven at scale.

## 6. What HOLDS (keep, with the real numbers)

- ✅ **Early intraday momentum (up>2 at 09:35) beats the field ~+0.3–0.4%/yr, every
  year.** Thin (win 51%, median +0.07%, tail-carried) — harvest across many names.
- ✅ **Oversold snapback** (buy the beaten pool the day *after* a down day, best when
  VIX already elevated): +0.84% after a −1% crash day, up to +1.43% with VIX>28. Real
  but year-dependent (fails calm trending years).
- ✅ **VIX>28 on a weak-open day = intraday knife.** Don't dip-buy into live deep fear.
- ✅ **The general instinct** that dip-buying is regime-sensitive — just far smaller
  and less clean than the 16-day sample implied.

---

## 7. Operating rules for the v2 brain (rewritten)

1. **Bias to the up-open pool, not the red pool.** The names already up >2% at 09:35
   on a healthy tape are the robust continuation pool; the red pool is a coin flip vs
   field. This reverses the old rule #2.
2. **Harvest momentum as a tail play.** up>2 wins on the mean via its right tail
   (earnings gap-and-go, news continuation). Expect ~51% hit rate; size for the tail,
   don't expect every name to pay.
3. **Only dip-buy the red pool with a causal reason:** yesterday was down (snapback),
   or it's a narrow one-group scare on an otherwise-fine tape. Don't dip-buy on the
   strength of a same-day regime label.
4. **Deep-fear gate:** weak open + VIX at the open > ~28 (or a sustained multi-day
   down-move) → the red pool is a knife. Abstain / defensive.
5. **Distrust same-day macro labels** (`spy_regime`, same-day `vix_close`) for any
   backward-looking "edge" — they leak the day's outcome. Condition only on prior-day /
   at-the-open values.
6. **The reclaim thesis is not an edge.** Do not build position sizing around "buy the
   red pool." At scale it is ~zero. The edge, such as it is, is momentum + snapback.

---

## 8. Methodology + open threads

- Analysis SQL ran over `intraday_bars_5m` in `data/trade_history.db`; per-symbol-day
  features (o930/p0935/close/dvol) aggregated in a scratch DB, joined to
  `macro_snapshots`. Liquidity filter dvol ≥ $50M (median liquid name ≈ $157M/day).
- **Look-ahead was the biggest trap** and is the transferable lesson: any macro label
  stamped at the close (regime, vix_close, breadth-at-close) will manufacture a fake
  "regime edge" because it co-moves with the very forward return you're predicting.
  Only condition on values fixed before/at the open.
- **Untested / next:** the `market_breadth` table (per CLAUDE.md) may hold intraday
  breadth (ad_ratio, pct_above_20d) usable as a *causal* 10:00 confirmation signal —
  worth testing the "reclaim count building by 10:00" claim properly. Also worth: does
  the up>2 momentum edge survive realistic entry slippage at 09:35, and does an
  up>2 × prior-day-up interaction sharpen it.

See also memory: `ai-trader-day-model-v2` (now superseded by this scale-validated
version), `ai-trader-daily-bid-group`, `ai-trader-last-mile-rule`.

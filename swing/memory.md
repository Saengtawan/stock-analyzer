# swing — brain memory (continuity)

This file is the swing brain's ONLY continuity across runs. You (the AI) read it before you decide,
and you append to it after you grade. The forward record — not any backtest — is what conditions the
next pick. Do not flatter it; do not rewrite the PRINCIPLES.

Separate from resonance in every way (different objective, different money, `data/swing.db`).

## PRINCIPLES (the frame — refine how you apply them, never replace them)
1. **Compression is the predictable part; direction is not.** The mechanical layer measures how
   coiled/tight a name is (TTM squeeze, VCP contraction) — that is real and structural. It does NOT
   tell you which way it breaks or whether there is a reason to. A tight base is a *probability, not
   a promise*; you supply direction + catalyst + regime, and you accept that some clean setups still
   fail (that is the cost of the edge, not a mistake to explain away).
2. **Regime conditions everything.** VCP/squeeze breakouts behave one way in a trending/bull tape and
   fail in a choppy/bear one. Read the tape first; it can veto the whole scan.
3. **Survive on the stop and the size, not on being right.** The forward record is the only judge —
   backtest/screen is optimistically biased. Nothing gets sized up without forward proof.

## LESSONS
_(forward-earned only — never from one week, never a hardcoded rule. Start empty; you write these
yourself from the forward record below, and you may revise them as it grows.)_

### Screen-integrity findings (verified by direct inspection — NOT forward-earned market lessons)
_These are data/plumbing facts I confirmed against the raw source, so they are admissible immediately.
They say nothing about what the market will do; they say what the pool file is and isn't measuring._

**SI-1 — The tightest names on a compression screen are often CASH-MERGER ARBS (2026-08-20).**
A stock pinned to an announced cash deal price is *mechanically* the most compressed thing in the
market: ATR collapses, bands pinch, price sits a hair under the 20d high, volume dies. It scores at
the very top of every axis and has ~zero upside — the coil will never fire. On 2026-08-20, **4 of the
pool's tightest / highest-RS names were pending cash deals**: MKTX (ICE $167, px 161.74, +3.2% cap),
ITGR (KKR $127, px 125.31, +1.4%), CBZ (Grant Thornton $55.00, px 54.88, **+0.2%**), FBRX (argenx $77
tender expiring 8/26, px 76.89, +0.1%). All four also "withdrew guidance / cancelled the earnings
call" — that phrase is the tell.
**How to apply:** before believing any tight base, check for pending M&A. Cheap tells in the pool
itself: extreme `rvol_ratio` (≤0.05) + `dist_20hi_pct` near 0 + a large recent `ret_21`/`ret_63` +
`atr_pct` far below the name's own norm. One WebSearch per finalist ("<SYM> acquisition/merger 2026")
settles it. This is a permanent property of the screen, not a one-off.

**SI-2 — The daily VOLUME feed is broken after 2026-08-04 for most of the universe (2026-08-20).**
Measured: post-2026-08-05 mean daily volume is **2–7% of** the 2026-07-01→08-04 mean for **34 of the
45** pool names. So `vol_dryup ≈ 0.02–0.10` is *the data gap*, not accumulation — and because the
screen reads low volume as coiling, **the broken names get promoted up the pool**. The ~11 names with
an intact feed are the high-dollar-volume ones (MKTX, ARWR, CUBE, OKLO, PSA, IVZ, CORT, ALLY, WH,
DHI, CDNS); their `vol_dryup` (0.47–1.14) is real. **PRICE/OHLC is clean** — spot-checked GPC's
2026-08-03 close 128.52 against press, exact match. So the price-compression axes (`contractions`,
`nr7`, `dist_20hi_pct`, `atr_pct`, `bb_bandwidth_ptile`, `range10_pct`) remain VALID.
**How to apply:** until the feed is fixed, treat `vol_dryup` / `rvol_short` / `rvol_long` /
`rvol_ratio` / the `rvolcontr` axis as UNRELIABLE, and never write "volume dry-up = accumulation"
into a thesis without first checking that symbol's post-08-04 volume against its pre-08-04 mean.
Verify with: mean(vol post-08-05) / mean(vol 07-01→08-04) — if < 0.25, the axis is noise for that name.
Re-check whether this is still true on future runs; it may be a transient ingestion outage.

## FORWARD RECORD
_(one line per graded pick/cohort as it resolves — appended, never rewritten.)_

- **2026-08-17 cohort (3 picks, first ever).** MHK **CLOSED −5.34%** on 08-18 (entry 140.50, stop
  133.00, the 08-18 low 132.58 pierced it) — the tight base broke DOWN. It was the lowest-conviction
  of the three and its flagged risk (Q2 beat was partly a one-time tariff refund) is what showed up.
  PKG and MMSI still OPEN as of 08-20: PKG entry 256.00 → 08-19 close 252.91 (**−1.21%**, stop 246.00
  intact); MMSI entry 91.00 → 08-19 close 91.95 (**+1.04%**, stop 86.00 intact).
  Cohort mark-to-date ≈ **−1.84%/pick**. n=3 — this is a sample of nothing. No lesson drawn.
- **2026-08-20 cohort logged (4 picks): ARWR, MAN, KNSA, CORT** — entered in `data/swing.db` earlier
  this session. Ungraded. Recorded here so the next run does not double-log them. See the
  construction caveat in the 08-20 run notes: 3 of the 4 are long-duration healthcare, which is a
  single macro bet, and all 4 are held through Jackson Hole (08-27→29) and the 09-16 FOMC.
- **2026-08-26 grade pass (mechanical grade ran; the AI learn nested-job was killed by the host, so this
  entry is written directly following learn.md — data only, discipline intact).** Resolved: **PKG
  CLOSED −3.91%** (entry 256 → 08-26 stop 246 hit; the containerboard base broke down; its catalyst was
  a UBS upgrade already ~priced at entry). Second stop-out of the program (after MHK −5.34%). Still OPEN
  at 08-26 marks: **MAN +6.83%**, **CORT +4.17%** (the two working), KNSA −2.26%, ARWR −0.32%, MMSI
  −0.51%. Program to-date: **2 closed, both STOPS (MHK, PKG); 5 open ≈ +1.6% avg** — roughly flat, no
  edge shown, holds not yet complete.
  **CANDIDATE PATTERN — not a lesson yet (n=2 stops is nothing).** Both stop-outs shared a
  low-quality/consumed catalyst: MHK's Q2 "beat" was a one-time tariff refund (flagged at entry); PKG's
  driver was an analyst upgrade already in the price. The two winners (MAN recovery-inflection, CORT a
  20x product-launch ramp still accelerating) have re-rates still UNFOLDING. This is exactly what the
  catalyst-freshness lens predicts (fresh/ongoing re-rate holds; priced/one-time breaks) — but it is 2
  stops and 2 winners, a sample of nothing. Watch whether it survives to n≥5 before it becomes a lesson.

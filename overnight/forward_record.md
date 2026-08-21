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

# resonance — MY (assistant/user) analysis & running commentary

Kept OUT of the auto-memory (`.claude/.../memory/MEMORY.md`) on purpose: the resonance cron's
`claude -p` session gets MEMORY.md injected, so any of MY conclusions/interpretation about the AI's
behavior there would condition its own judgment (a feedback loop). These are notes for the human
side (me + user) only — Read this file explicitly when needed; it is NOT auto-loaded anywhere.
Neutral FACTS the AI legitimately needs (winLo rule, data gotchas) stay in MEMORY.md.

Moved here 2026-08-18.

---

## Intervention posture (resonance)
- **system must have a stronger heart than us** (see memory/feedback_system_stronger_heart.md) —
  2026-08-16: the edge IS unemotional discipline through losses that scare humans. If it pulls back
  from its own edge on ONE loss / a grading artifact (not a repeated record), that's a recency wobble
  worth a look, not a genuine update — distinguish a real update (fails across MULTIPLE days) from a
  recency reaction, and step in only on the latter, via Door A (pm-path at CLOSE, never at decide).
  Default is: let it run while results are good; this is a watch note, not a verdict on the AI.

---

## resonance — LIVE WEEK 1 (2026-08-03 → 08-07)
First real forward week. Picks (by system >+2% bar): **3 win / 1 loss** — INSM +3.11, MGNI +5.79,
TEAM +2.20 (win); CART +0.34 (green but under bar = loss). All beat SPY; 08-06 picks won on a RED
SPY day = real alpha, not beta. Notable correct-skips: DOCS −29% / SOUN −12% / CLRO −16% (extreme-gap
froth), ROKU (merger-arb pinned to Fox $160 takeout → beat irrelevant). = first system to start
forward POSITIVE (old: ai_trader −2.30 / riser −0.29). N tiny (4 picks/5 days) — not proven.
- **Pipeline all fixed this week** (was silently degraded → 3 forced abstains 08-03/04/05): premarket
  SIP+IEX (cap now−16m), update_daily retry+IEX, grader SIP self-heal + load_dotenv, busy_timeout,
  build_universe guard+retry, consol relative (no hardcode), ETF exclusion. Runs clean on cron now.
- **gain-bias REMOVED** from memory.md #3 / decide.md (was "high gain=froth" blanket) → AI now buys
  gapped-hard-catalysts (the winners). Matches AI's own L2 (gap doesn't consume range).
- **AI is autonomous + self-improving**: writes L1/L2/L3 itself (learn.sh, cron-isolated), and on
  08-07 SELF-REPAIRED execute.py (added load_dotenv, timestamp 03:32=learn run, no human).
- **⚠️⚠️ coil DEMOTED by AI itself — L4 written 2026-08-10.** After 6 picks/3 days: coiled 1-1,
  UNCOILED catalyst-only 3-1 (INSM/TEAM/MNDY win, ACHR loss); loaded_spring didn't separate MNDY(#1)
  from ACHR(#26) same day. AI's L4: "coil axes have not discriminated winner from loser; the catalyst
  has → STOP using coil presence/absence as take/pass reason; reason on catalyst direction+durability."
  Hedged (keeps #1 magnitude/coin-flip logic + L1 inert-coil; sample=6). = the AI revised the system's
  FOUNDING premise (coil, the "resonance" namesake) from its own forward record. This is the concrete
  answer to "can AI replace the rules we wrote" — YES, it just did, to principle #1.
- **L3 (down-gapper rebound) FIRST WIN: MNDY +9.30% (08-10, #1 of 35 in pool)** — AI missed TTD 08-07,
  wrote L3, applied it to MNDY, won big. Self-derived lesson → real money. Picks now 6: avg +3.05%,
  5/6 green (INSM+3.11/MGNI+5.79/TEAM+2.20/MNDY+9.30 win, CART+0.34 under-bar, ACHR−2.42 loss).
- **⚠️ SUPERSEDED note: coil thesis being CONTRADICTED by its own winners** — TEAM/INSM won CATALYST-ONLY
  (not coiled, atr 0.5+), while the clean coil (CART/MGNI mixed) under-performed. AI flagged it, not
  yet hardened to L4. Watch: coil may drop to optional if catalyst-only keeps winning.
- L3 (post-earnings down-gapper rebound) tested 08-07: AI evaluated TTD, declined, it ran +6.90% (miss).

## LUNR / L5 (2026-08-17)
LUNR pick (L5 unspent-auction override of its own discharge check) closed +0.64% = green but under
the +2% bar = a system loss. The AI's OWN learn pass nailed it: caught itself violating L7 (arguing
past a this-name risk with a cohort analogy), graded it a loss, and refined the concept — "unspent is
necessary NOT sufficient; what must be unspent is a CURRENT-NUMBERS REMODEL (earnings → desks finish a
model → holds to close), not ATTENTION (a multi-year award → momentum money → fades the afternoon)."
L5 distant-payout 0-for-3, L7 override 0-for-5. Also owned that its stated falsifiable was mis-specified
("if closes red" when the bet is the +2% bar). = the learn loop working; lessons self-earned, not mine.
Entry note: the AI's pre-open winLo estimate band 19.5-19.7 was ACCURATE — LUNR dipped intraday to
19.50, into the band. winLo 19.77 → limit 20.07 filled the dip for +1.60% vs +0.64% at open (still
under the +2% bar). The limit strategy validated live; SIP matched yfinance winLo to ~1 cent.

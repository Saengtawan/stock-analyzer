"""scripts/audit_resonance_plan.py — did the decide agent actually FOLLOW the rebuilt process?

The record's core failure mode is compliance theater: every losing pick cited every gate by name and
still lost, because prose gates cannot fail a fluent writer. After the 09-03 rebuild (mechanical
`shortlist` in the pool + the agent's job reduced to TAKE/VETO with a context read), this script checks
the plan MECHANICALLY instead of trusting the prose:

  1. did the plan pick from the pool's computed `shortlist`, or off it?
  2. if off-shortlist, did it state that + give an override reason (G6)?
  3. did it do the Step-3 context read (news/edgar/veto language), not just cite gates?
  4. gate-citation count — high citations + off-shortlist pick = the old theater pattern.

Usage:  python scripts/audit_resonance_plan.py [YYYY-MM-DD]
Read-only. Prints a short verdict; writes nothing.
"""
from __future__ import annotations
import json, sys, os, datetime, zoneinfo

ET = zoneinfo.ZoneInfo("America/New_York")
date = sys.argv[1] if len(sys.argv) > 1 else datetime.datetime.now(ET).strftime("%F")
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
plan_p = f"{root}/resonance/plans/{date}.plan.json"
pool_p = f"{root}/resonance/cache/pool_{date}.json"
for p in (plan_p, pool_p):
    if not os.path.exists(p):
        print(f"missing: {p}"); sys.exit(1)

plan = json.load(open(plan_p)); pool = json.load(open(pool_p))
short = [d["sym"] for d in (pool.get("shortlist") or [])]
picks = [p.get("sym") for p in (plan.get("picks") or [])]
blob = json.dumps(plan).lower()

print(f"=== resonance plan audit {date} ===")
print(f"  pool shortlist ({len(short)}): {', '.join(short) if short else '(empty)'}")
print(f"  picks ({len(picks)}): {', '.join(picks) if picks else 'ABSTAIN'}")

if not picks:
    print("  → ABSTAIN. valid outcome; nothing to audit on selection.")
else:
    on = [s for s in picks if s in short]; off = [s for s in picks if s not in short]
    print(f"  ON-shortlist: {on or '—'}   OFF-shortlist: {off or '—'}")
    if off:
        said = ("off-shortlist" in blob) or ("shortlist" in blob and "override" in blob)
        print(f"  G6 override stated in writing? {'YES' if said else '❌ NO — silent off-shortlist pick (the old failure)'}")

# Step-3 context read: is there evidence it read what the news SAYS (not just cited gates)?
ctx = [k for k in ("downgrade", "price target", "pt cut", "insider", "websearch", "edgar",
                   "guidance cut", "analysts", "veto", "negative catalyst") if k in blob]
print(f"  context-read markers: {', '.join(ctx) if ctx else '❌ none'}")
gates = sum(blob.count(g) for g in ("g1", "g2", "g3", "g4", "g5", "g6"))
print(f"  gate citations: {gates}")
if picks and gates >= 6 and not ctx:
    print("  ⚠️ COMPLIANCE THEATER SHAPE: many gate citations, no evidence of an actual context read.")
print("  (forward outcome, not the prose, is the judge — grade at 15:55 ET)")

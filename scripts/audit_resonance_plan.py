"""scripts/audit_resonance_plan.py — did the decide agent actually FOLLOW the rebuilt process?

The record's core failure mode is compliance theater: every losing pick cited every gate by name and
still lost, because prose gates cannot fail a fluent writer. So this checks the plan MECHANICALLY
instead of trusting its prose.

Updated 2026-09-04 for the movement-concentration pool. The old `shortlist` check is GONE and is not
replaced: the shortlist now equals the pool (the pond is admitted on exactly the dimensions the
shortlist used to mark), so "on/off shortlist" no longer carries information. What replaced it as the
real discipline is the COHORT BASELINE — the pool is near-symmetric by construction, so a plan that
cannot say why its picks beat the pond's own up-rate has not made a decision, it has drawn a ticket.

  1. are the picks actually in today's pool?
  2. does the plan ENGAGE the cohort baseline (state the bar it has to beat)?
  3. did it do the Step-3 context read (news/edgar/veto language), not just cite gates?
  4. gate-citation count — many citations + no context read = the old theater pattern.

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
pooled = {d["sym"] for d in (pool.get("digest") or [])}
base = pool.get("cohort_baseline") or {}
picks = [p.get("sym") for p in (plan.get("picks") or [])]
blob = json.dumps(plan).lower()

print(f"=== resonance plan audit {date} ===")
print(f"  pool: {len(pooled)} names   mode={pool.get('pool_mode','?')}")
if base:
    print(f"  cohort baseline (last {base.get('sessions')} sessions): "
          f"UP {base.get('up_pct')}%  DOWN {base.get('down_pct')}%  <- the bar")
else:
    print("  cohort baseline: not measurable yet")
print(f"  picks ({len(picks)}): {', '.join(picks) if picks else 'ABSTAIN'}")

if not picks:
    # An abstain still owes a decision. decide.md requires `closest_call` on every abstain — the one
    # name the pass would have taken if forced — and learn.md grades it. Without it a run of abstains
    # produces no gradable decision at all, which is how the record learned nothing from nine of them.
    cc = plan.get("closest_call")
    print(f"  closest_call: {str(cc)[:110] if cc else '[X] MISSING — this abstain is ungradable'}")
    print("  -> ABSTAIN. valid outcome; nothing to audit on selection.")
else:
    off = [s for s in picks if s not in pooled]
    if off:
        print("  [X] NOT IN POOL: %s -- the plan picked outside its own candidate set." % off)
    else:
        print("  all picks are in today's pool.")
    engaged = any(k in blob for k in ("baseline", "base rate", "cohort", "up-rate", "beat the pool"))
    _v = "YES" if engaged else "NO \u2014 no stated bar to beat"
    print(f"  engages the cohort baseline? {_v}")

# Step-3 context read: is there evidence it read what the news SAYS (not just cited gates)?
ctx = [k for k in ("downgrade", "price target", "pt cut", "insider", "websearch", "edgar",
                   "guidance cut", "analysts", "veto", "negative catalyst") if k in blob]
print(f"  context-read markers: {', '.join(ctx) if ctx else '❌ none'}")
gates = sum(blob.count(g) for g in ("g1", "g2", "g3", "g4", "g5", "g6"))
print(f"  gate citations: {gates}")
if picks and gates >= 6 and not ctx:
    print("  ⚠️ COMPLIANCE THEATER SHAPE: many gate citations, no evidence of an actual context read.")
print("  (forward outcome, not the prose, is the judge — grade at 15:55 ET)")

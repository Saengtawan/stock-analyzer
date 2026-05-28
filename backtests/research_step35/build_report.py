"""Build the final report after Step 35-C run completes.

Run after /tmp/step35_C/comparison.csv exists.
Produces: /tmp/step35_C/report.md
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

OUT = Path('/tmp/step35_C')
csv = OUT / 'comparison.csv'
if not csv.exists():
    print(f"NOT_READY: {csv} missing")
    sys.exit(1)

df = pd.read_csv(csv)
df = df.set_index(['config','zone'])

# Per-month ledger (for sanity)
led = pd.read_csv(OUT / 'trades_ledger.csv') if (OUT / 'trades_ledger.csv').exists() else None


def row(z, cfg):
    r = df.loc[(cfg, z)]
    return r


def fmt(r):
    if pd.isna(r['WR']):
        return "  -    -      -       -      -"
    return (f"{int(r['N']):>4d}  {r['WR']*100:>4.0f}% "
            f"{r['avg']:>+6.2f}%  {r['total']:>+7.1f}%  {r['worst']:>+6.2f}%")


# Build markdown
lines = []
lines.append("# Step 35-C: Z1 Recipe Universal Test\n")
lines.append("**Question:** If Z1's recipe (label_z12_market_3dd / Z1 HPs / R9 / "
             "THR=0.60) is applied to all zones, do Z2/Z3/Z4 also reach ~100% WR?\n")
lines.append("**Methodology:** Walk-forward, 8 monthly refits, 2025-09 → 2026-04, "
             "TRUE-OOS (each month trains on prior 840d, tests on month).\n")
lines.append("**Note:** `label_z12_market_3dd` is only defined for mfo ≤ 29 in pkl. "
             "For Z3/Z4 we synthesize the union with `label_z34_market` — both use "
             "the IDENTICAL formula (EOD > scan × 0.998 AND no -3% intraday DD), "
             "just restricted to different mfo ranges. So the experiment really tests "
             "the {label-formula × HPs × ranking} bundle, not just the literal column.\n")
lines.append("## Per-zone comparison (8-month walk-forward)\n")
lines.append("| Zone | Config       |    N |   WR |    avg |   total |  worst |")
lines.append("|------|--------------|------|------|--------|---------|--------|")
for z in ['Z1','Z2','Z3','Z4']:
    for cfg in ['current','z1_recipe']:
        r = row(z, cfg)
        if pd.isna(r['WR']):
            lines.append(f"| {z} | {cfg:12s} |    0 |   -  |   -    |    -    |   -    |")
        else:
            lines.append(f"| {z} | {cfg:12s} | {int(r['N']):>4d} | "
                         f"{r['WR']*100:>3.0f}% | {r['avg']:>+5.2f}% | "
                         f"{r['total']:>+6.1f}% | {r['worst']:>+5.2f}% |")

# Deltas
lines.append("\n## Z1-recipe Δ vs current (per zone)\n")
lines.append("| Zone | ΔWR (pp) | Δavg (pp) | Δtotal (pp) | Δworst (pp) | verdict |")
lines.append("|------|---------:|----------:|------------:|------------:|:--------|")
for z in ['Z1','Z2','Z3','Z4']:
    c = row(z, 'current')
    r = row(z, 'z1_recipe')
    if pd.isna(c['WR']) or pd.isna(r['WR']):
        lines.append(f"| {z} | n/a | n/a | n/a | n/a | n/a |")
        continue
    dwr = (r['WR'] - c['WR']) * 100
    davg = r['avg'] - c['avg']
    dtot = r['total'] - c['total']
    dworst = r['worst'] - c['worst']
    verdict = "improves" if dtot > 0 and dwr >= -1 else \
              ("comparable" if abs(dtot) < 30 and abs(dwr) < 2 else "regresses")
    lines.append(f"| {z} | {dwr:+5.1f} | {davg:+5.2f} | {dtot:+7.1f} | "
                 f"{dworst:+5.2f} | {verdict} |")

# 100% WR test
lines.append("\n## Did Z1-recipe achieve ~100% WR universally?\n")
for z in ['Z1','Z2','Z3','Z4']:
    r = row(z, 'z1_recipe')
    if pd.isna(r['WR']):
        lines.append(f"- **{z}**: no picks (skip)")
        continue
    target = r['WR'] >= 0.98
    lines.append(f"- **{z}**: WR={r['WR']*100:.0f}% — "
                 f"{'YES, ~100% achieved' if target else 'NO, falls short'}")

# Recommendation
lines.append("\n## Recommendation\n")
# Compute combined totals
cur_total = df.loc['current']['total'].sum()
r_total = df.loc['z1_recipe']['total'].sum()
cur_wr = (df.loc['current']['WR'] * df.loc['current']['N']).sum() / df.loc['current']['N'].sum()
r_wr = (df.loc['z1_recipe']['WR'] * df.loc['z1_recipe']['N']).sum() / df.loc['z1_recipe']['N'].sum()
lines.append(f"- Combined current: WR={cur_wr*100:.1f}% total={cur_total:+.0f}%")
lines.append(f"- Combined z1_recipe: WR={r_wr*100:.1f}% total={r_total:+.0f}%\n")

if r_total > cur_total * 1.05 and r_wr >= cur_wr - 0.01:
    rec = ("**DEPLOY as Step 35**: Z1-recipe universalization beats current "
           "production. Bug was label/ranking choice, not mfo timing.")
elif r_total < cur_total * 0.95 or r_wr < cur_wr - 0.02:
    rec = ("**DO NOT DEPLOY**: Z1-recipe regresses meaningfully. Current "
           "zone-specific tuning (labels + HPs + ranking) genuinely fits the "
           "different mfo timing regimes — this is label-zone interaction, "
           "not a one-size-fits-all opportunity.")
else:
    rec = ("**INCONCLUSIVE / borderline**: Z1-recipe ≈ current production "
           "on aggregate. No deploy reason. Means Z1's ~100% WR is partly "
           "intrinsic to Z1's mfo (0-9) range, not a label artifact transferable "
           "to other zones.")
lines.append(rec)

# Stress-month note
if led is not None:
    nov = led[led['date'].str.startswith('2025-11')]
    if len(nov):
        lines.append(f"\n*Stress month sanity (2025-11, VIX/regime shock):* "
                     f"current Z1 WR={nov[(nov.zone=='Z1')&(nov.config=='current')]['pnl'].apply(lambda x:x>0).mean()*100:.0f}%, "
                     f"z1_recipe Z1 WR={nov[(nov.zone=='Z1')&(nov.config=='z1_recipe')]['pnl'].apply(lambda x:x>0).mean()*100:.0f}%.")

report = "\n".join(lines)
(OUT / 'report.md').write_text(report)
print(report)
print(f"\nSaved: {OUT/'report.md'}")

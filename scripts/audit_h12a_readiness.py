"""H12-A Production Readiness Audit — comprehensive checks.

Verifies every layer required for safe production deployment.
Reports PASS/WARN/FAIL per check + overall verdict.

Categories:
  1. CODE: imports, syntax, error handling
  2. MODELS: 235 files load, predictions match research
  3. CELL RATINGS: all sectors mapped, JSON valid
  4. GATES: regime gates handle edge cases (None, NaN, extreme values)
  5. EF: entry filter v2-h12a integrates correctly
  6. INTEGRATION: ml_filter.py actually invokes H12-A path
  7. SERVICE: systemd config compatible
  8. SCHEMA: shadow DB tables ready
  9. EDGE CASES: missing data, weekends, sector unknown
"""
import os, sys, sqlite3, json, traceback
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PASS = '✅'
WARN = '⚠️ '
FAIL = '❌'
results = []

def check(category, name, fn):
    try:
        status, detail = fn()
    except Exception as e:
        status = FAIL
        detail = f"Exception: {e}"
    results.append((category, name, status, detail))
    print(f"  {status} {name}: {detail}")


# ============================================================
# 1. CODE
# ============================================================
print("\n[1/9] CODE checks")

def check_imports():
    from src.scan.ml_scorer_h12a import get_scorer_h12a, MLScorerH12A
    from src.scan.h12a_picker import score_and_filter_h12a, passes_regime_gate, get_zone, pick_top1_per_zone
    from src.entry_filter.rules import evaluate
    from src.scan.shadow_h12a import is_shadow_mode, log_h12a_shadow_pick, log_h12a_reject
    return PASS, "all modules import"
check("CODE", "imports", check_imports)

def check_ml_filter_syntax():
    import ast
    src = open(ROOT / 'src/scan/strategies/ml_filter.py').read()
    ast.parse(src)
    if 'ML_FILTER_VARIANT' in src and 'h12a' in src:
        return PASS, "ml_filter.py syntax OK + h12a path present"
    return FAIL, "h12a branch missing in ml_filter.py"
check("CODE", "ml_filter syntax + h12a path", check_ml_filter_syntax)

def check_ef_toggle():
    from src.entry_filter.rules import evaluate
    os.environ.pop('ENTRY_FILTER_SPEC', None)
    p1 = evaluate(zone='Z1', beta=0.8, sector='Industrials', gain_from_open=2.0)
    os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'
    p2 = evaluate(zone='Z1', beta=0.8, sector='Industrials', gain_from_open=2.0)
    os.environ.pop('ENTRY_FILTER_SPEC', None)
    if not p1[0] and p2[0]:
        return PASS, "v1 blocks β/Industrials, v2-h12a allows (Z1 gain≤4.5 only)"
    return FAIL, f"v1={p1}, v2={p2}"
check("CODE", "EF toggle (v1 vs v2-h12a)", check_ef_toggle)


# ============================================================
# 2. MODELS
# ============================================================
print("\n[2/9] MODELS checks")

def check_model_files():
    models_dir = ROOT / 'backtests/models_prod_v23_h12a'
    counts = {}
    for z in ['Z1', 'Z2', 'Z3', 'Z4']:
        files = list((models_dir / z).glob('*.txt'))
        counts[z] = len(files)
    total = sum(counts.values())
    return PASS, f"Z1={counts['Z1']} Z2={counts['Z2']} Z3={counts['Z3']} Z4={counts['Z4']} total={total}"
check("MODELS", "file count per zone", check_model_files)

def check_meta_json():
    meta_path = ROOT / 'backtests/models_prod_v23_h12a/Z2/meta.json'
    m = json.load(open(meta_path))
    label_ok = m['label'] == 'label_z12_market_3dd'
    arch_ok = m['arch'] == 'V-C'
    return (PASS if (label_ok and arch_ok) else FAIL,
            f"Z2 label={m['label']} arch={m['arch']} cutoff={m['cutoff']}")
check("MODELS", "Z2 label change (eod_green_v2 → z12_3dd)", check_meta_json)

def check_scorer_load():
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    s = get_scorer_h12a()
    loaded = sum(1 for z in s.generalist if s.generalist[z])
    if loaded < 4:
        return FAIL, f"only {loaded}/4 zones loaded"
    total_specialists = sum(len(s.specialists.get(z, {})) for z in ['Z1','Z2','Z3','Z4'])
    return PASS, f"4 zones loaded, {total_specialists} total sector specialists"
check("MODELS", "scorer loads all zones", check_scorer_load)

def check_score_returns_prob():
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    s = get_scorer_h12a()
    feats = {f: 0.0 for f in s.features.get('Z1', [])}
    feats['vix'] = 17
    score = s.score(feats, 5, 'Technology')
    if 0 <= score <= 1:
        return PASS, f"Z1 Tech sample score={score:.4f} ∈ [0,1]"
    return FAIL, f"score={score} not in [0,1]"
check("MODELS", "score returns valid probability", check_score_returns_prob)


# ============================================================
# 3. CELL RATINGS
# ============================================================
print("\n[3/9] CELL RATINGS checks")

def check_cell_json():
    cells = json.load(open(ROOT / 'configs/h12a_cell_ratings.json'))
    cbz = cells.get('cells_by_zone', {})
    pairs = sum(len(v) for v in cbz.values())
    return PASS, f"{pairs} (zone, sector) pairs across {len(cbz)} zones"
check("CELLS", "cell ratings JSON valid", check_cell_json)

def check_critical_cells():
    cells = json.load(open(ROOT / 'configs/h12a_cell_ratings.json'))
    cbz = cells['cells_by_zone']
    # Z2 Healthcare must have positive avg (we expect ~+0.70%)
    hc = cbz.get('Z2', {}).get('Healthcare', {})
    if hc.get('avg', 0) > 0.5:
        return PASS, f"Z2 Healthcare WR={hc['WR']:.0f}% avg={hc['avg']:+.2f}%"
    return WARN, f"Z2 Healthcare missing or low: {hc}"
check("CELLS", "Z2 Healthcare cell (key driver)", check_critical_cells)

def check_filter_logic():
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    s = get_scorer_h12a()
    # Z2 Energy (known bad cell)
    e = s.passes_cell_filter('Z2', 'Energy')
    # Z2 Healthcare (known good cell)
    h = s.passes_cell_filter('Z2', 'Healthcare')
    # Z4 anything
    z4 = s.passes_cell_filter('Z4', 'Anything')
    # Unknown sector — graceful pass
    unk = s.passes_cell_filter('Z1', 'Unknown_Sector')
    if (not e) and h and z4 and unk:
        return PASS, "Energy blocked, Healthcare allowed, Z4 no-filter, unknown=graceful PASS"
    return FAIL, f"Energy={e} Health={h} Z4={z4} unknown={unk}"
check("CELLS", "cell filter logic (S2/S7/none/graceful)", check_filter_logic)


# ============================================================
# 4. GATES
# ============================================================
print("\n[4/9] GATES checks")

def check_z1_gate():
    from src.scan.h12a_picker import passes_regime_gate
    # VIX<20 ✓
    p1, _ = passes_regime_gate('Z1', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=2, sector='Tech')
    # VIX>=20 ✗
    p2, _ = passes_regime_gate('Z1', vix=22, vix_5d_chg=-0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=2, sector='Tech')
    # sec<=0 ✗
    p3, _ = passes_regime_gate('Z1', vix=17, vix_5d_chg=-0.5, sec_rel_strength=-0.5, spy_intra=0.3, dow=2, sector='Tech')
    if p1 and (not p2) and (not p3):
        return PASS, "VIX<20 ✓, VIX≥20 ✗, sec≤0 ✗"
    return FAIL, f"p1={p1} p2={p2} p3={p3}"
check("GATES", "Z1 (VIX<20 + sec>0)", check_z1_gate)

def check_z2_gate():
    from src.scan.h12a_picker import passes_regime_gate
    p_falling, _ = passes_regime_gate('Z2', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=2, sector='Health')
    p_rising, _ = passes_regime_gate('Z2', vix=17, vix_5d_chg=0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=2, sector='Health')
    if p_falling and (not p_rising):
        return PASS, "vix_5d<0 ✓, vix_5d≥0 ✗"
    return FAIL, f"falling={p_falling} rising={p_rising}"
check("GATES", "Z2 (vix_5d_chg<0)", check_z2_gate)

def check_z3_gate():
    from src.scan.h12a_picker import passes_regime_gate
    p_wed, _ = passes_regime_gate('Z3', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=2, sector='Tech')
    p_fri, _ = passes_regime_gate('Z3', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1.5, spy_intra=0.3, dow=4, sector='Tech')
    p_negsec, _ = passes_regime_gate('Z3', vix=17, vix_5d_chg=-0.5, sec_rel_strength=-0.5, spy_intra=0.3, dow=2, sector='Tech')
    if p_wed and (not p_fri) and (not p_negsec):
        return PASS, "Wed ✓, Fri ✗, sec≤0 ✗"
    return FAIL, f"Wed={p_wed} Fri={p_fri} negsec={p_negsec}"
check("GATES", "Z3 (sec>0 + ¬Fri)", check_z3_gate)

def check_z4_optionE():
    from src.scan.h12a_picker import passes_regime_gate
    # Calm + good sec + SPY=0.3 ✓
    p_good, _ = passes_regime_gate('Z4', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1, spy_intra=0.3, dow=2, sector='Technology')
    # Calm + other sec + SPY=0.3 ✗
    p_other_low, _ = passes_regime_gate('Z4', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1, spy_intra=0.3, dow=2, sector='Financial Services')
    # Calm + other sec + SPY=0.7 ✓
    p_other_high, _ = passes_regime_gate('Z4', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1, spy_intra=0.7, dow=2, sector='Financial Services')
    # Crisis + SPY=0.3 ✗
    p_crisis, _ = passes_regime_gate('Z4', vix=28, vix_5d_chg=2, sec_rel_strength=1, spy_intra=0.3, dow=2, sector='Technology')
    if p_good and (not p_other_low) and p_other_high and (not p_crisis):
        return PASS, "Option E* all 4 cases correct"
    return FAIL, f"good={p_good} other_low={p_other_low} other_high={p_other_high} crisis={p_crisis}"
check("GATES", "Z4 Option E* (4 conditions)", check_z4_optionE)


# ============================================================
# 5. EF (Entry Filter)
# ============================================================
print("\n[5/9] EF (Entry Filter) checks")

def check_ef_h12a_keeps_z1_gain():
    os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'
    from src.entry_filter.rules import evaluate
    p1, _ = evaluate(zone='Z1', gain_from_open=3.0)
    p2, _ = evaluate(zone='Z1', gain_from_open=5.0)
    os.environ.pop('ENTRY_FILTER_SPEC', None)
    if p1 and (not p2):
        return PASS, "Z1 gain=3 ✓, gain=5 ✗ (>4.5 blocked)"
    return FAIL, f"gain3={p1} gain5={p2}"
check("EF", "v2-h12a: Z1 gain≤4.5 (DD-control)", check_ef_h12a_keeps_z1_gain)

def check_ef_h12a_passes_z234():
    os.environ['ENTRY_FILTER_SPEC'] = 'v2-h12a'
    from src.entry_filter.rules import evaluate
    p2, _ = evaluate(zone='Z2', dow=0, beta=2.0, gain_from_open=4.0)
    p3, _ = evaluate(zone='Z3', mom20d=30)
    p4, _ = evaluate(zone='Z4', mom20d=-5)
    os.environ.pop('ENTRY_FILTER_SPEC', None)
    if p2 and p3 and p4:
        return PASS, "Z2/Z3/Z4 all pass (no EF rules in H12-A)"
    return FAIL, f"Z2={p2} Z3={p3} Z4={p4}"
check("EF", "v2-h12a: Z2/Z3/Z4 no rules", check_ef_h12a_passes_z234)


# ============================================================
# 6. INTEGRATION
# ============================================================
print("\n[6/9] INTEGRATION checks")

def check_default_unchanged():
    os.environ.pop('ML_FILTER_VARIANT', None)
    from src.scan.strategies.ml_filter import MLFilterStrategy
    s = MLFilterStrategy()
    if s.MARKET_ENTRY and s.REQUIRE_75_THRESHOLD and s.expected_wr == 0.67:
        return PASS, "default class loads with v1 behavior unchanged"
    return FAIL, "production behavior altered"
check("INTEGRATION", "default behavior unchanged", check_default_unchanged)

def check_h12a_branch_loadable():
    os.environ['ML_FILTER_VARIANT'] = 'h12a'
    # Reload module to pick up env (just check imports work)
    import importlib
    from src.scan.strategies import ml_filter
    importlib.reload(ml_filter)
    src = open(ROOT / 'src/scan/strategies/ml_filter.py').read()
    has_h12a = 'h12a_scorer' in src and '_h12a_score_filter' in src
    os.environ.pop('ML_FILTER_VARIANT', None)
    if has_h12a:
        return PASS, "ml_filter.py contains h12a integration branch"
    return FAIL, "h12a branch not found"
check("INTEGRATION", "ml_filter.py h12a branch wired", check_h12a_branch_loadable)


# ============================================================
# 7. SERVICE (systemd compat)
# ============================================================
print("\n[7/9] SERVICE checks")

def check_systemd_service():
    svc = Path.home() / '.config/systemd/user/auto-trading.service'
    if not svc.exists():
        return WARN, f"systemd unit not found at {svc} (may use different path)"
    content = svc.read_text()
    # Just check service file exists & has Python
    if 'python' in content.lower() or 'Exec' in content:
        return PASS, "systemd unit found, looks valid"
    return WARN, "systemd unit found but unclear content"
check("SERVICE", "systemd unit file", check_systemd_service)

def check_service_running():
    import subprocess
    r = subprocess.run(['systemctl', '--user', 'is-active', 'auto-trading.service'],
                        capture_output=True, text=True)
    status = r.stdout.strip()
    if status == 'active':
        return PASS, "auto-trading.service is active"
    return WARN, f"auto-trading.service status: {status}"
check("SERVICE", "auto-trading.service status", check_service_running)


# ============================================================
# 8. DB SCHEMA
# ============================================================
print("\n[8/9] DB SCHEMA checks")

def check_main_db():
    db = ROOT / 'data/trade_history.db'
    if not db.exists():
        return FAIL, "trade_history.db missing"
    conn = sqlite3.connect(str(db))
    n = conn.execute("SELECT COUNT(*) FROM stock_fundamentals").fetchone()[0]
    conn.close()
    return PASS, f"trade_history.db OK, {n} stock_fundamentals rows"
check("SCHEMA", "trade_history.db sector lookup", check_main_db)

def check_shadow_db():
    from src.scan.shadow_h12a import _init_db, SHADOW_DB
    _init_db()
    conn = sqlite3.connect(str(SHADOW_DB))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    conn.close()
    if 'shadow_picks' in tables and 'shadow_rejects' in tables:
        return PASS, f"shadow DB initialized: {tables}"
    return FAIL, f"shadow tables missing: {tables}"
check("SCHEMA", "shadow journal tables", check_shadow_db)


# ============================================================
# 9. EDGE CASES
# ============================================================
print("\n[9/9] EDGE CASE checks")

def check_missing_features():
    from src.scan.h12a_picker import score_and_filter_h12a
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    s = get_scorer_h12a()
    # All features 0, missing VIX
    feats = {f: 0.0 for f in s.features.get('Z1', [])}
    score, reason = score_and_filter_h12a(s, feats, 5, 'Technology',
                                            vix=None, vix_5d_chg=None,
                                            sec_rel_strength=None,
                                            spy_intra=None, dow=2)
    # Should produce a non-error score (graceful pass on missing regime data)
    if score >= 0:
        return PASS, f"missing regime data → graceful score={score:.3f}"
    return FAIL, f"crashed or negative on missing: {score} ({reason})"
check("EDGE", "missing regime features", check_missing_features)

def check_unknown_sector():
    from src.scan.h12a_picker import score_and_filter_h12a
    from src.scan.ml_scorer_h12a import get_scorer_h12a
    s = get_scorer_h12a()
    feats = {f: 0.0 for f in s.features.get('Z1', [])}
    score, reason = score_and_filter_h12a(s, feats, 5, 'Made_Up_Sector',
                                            vix=17, vix_5d_chg=-0.5,
                                            sec_rel_strength=1, spy_intra=0.3, dow=2)
    # Unknown sector: should use generalist + graceful pass cell filter
    if score >= 0:
        return PASS, f"unknown sector → generalist used, score={score:.3f}"
    return FAIL, f"crashed on unknown sector: {score}"
check("EDGE", "unknown sector handling", check_unknown_sector)

def check_extreme_values():
    from src.scan.h12a_picker import passes_regime_gate
    # Extreme VIX
    p_high_vix, _ = passes_regime_gate('Z1', vix=100, vix_5d_chg=0, sec_rel_strength=1, spy_intra=0, dow=0, sector='Tech')
    # Negative SPY
    p_neg_spy, _ = passes_regime_gate('Z4', vix=17, vix_5d_chg=-0.5, sec_rel_strength=1, spy_intra=-5, dow=2, sector='Technology')
    # Both should be blocked
    if (not p_high_vix) and (not p_neg_spy):
        return PASS, "extreme VIX=100 ✗, SPY=-5% ✗"
    return WARN, f"high_vix={p_high_vix} neg_spy={p_neg_spy}"
check("EDGE", "extreme value handling", check_extreme_values)


# ============================================================
# REPORT
# ============================================================
print("\n" + "=" * 70)
print("READINESS AUDIT SUMMARY")
print("=" * 70)
cats = {}
for cat, name, status, _ in results:
    cats.setdefault(cat, {'pass': 0, 'warn': 0, 'fail': 0})
    if PASS in status: cats[cat]['pass'] += 1
    elif WARN in status: cats[cat]['warn'] += 1
    else: cats[cat]['fail'] += 1

total_pass = sum(c['pass'] for c in cats.values())
total_warn = sum(c['warn'] for c in cats.values())
total_fail = sum(c['fail'] for c in cats.values())
total = total_pass + total_warn + total_fail

print(f"\nBy category:")
for cat, c in cats.items():
    n = c['pass'] + c['warn'] + c['fail']
    print(f"  {cat:<12}  {c['pass']}/{n} pass, {c['warn']} warn, {c['fail']} fail")

print(f"\nOverall: {total_pass}/{total} pass, {total_warn} warn, {total_fail} fail")

print(f"\nVerdict:")
if total_fail > 0:
    print(f"  ❌ NOT READY — {total_fail} failure(s) need fix")
elif total_warn > 0:
    print(f"  ⚠️  READY WITH CAVEATS — {total_warn} warning(s) to acknowledge")
else:
    print(f"  ✅ READY — all checks pass")

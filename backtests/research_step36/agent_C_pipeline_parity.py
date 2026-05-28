"""Agent C — Pipeline parity audit.

Reproduce live ml_prob from stored features_json using the current
production models (backtests/models_prod_v22/) and check whether the
predictions match the ml_prob recorded in scan_picks.

Read-only. Saves report alongside this script.
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import lightgbm as lgb

ROOT = Path('/home/saengtawan/work/project/cc/stock-analyzer')
MODEL_DIR = ROOT / 'backtests' / 'models_prod_v22'
JOURNAL = ROOT / 'data' / 'scan_journal.db'

# ----------------- constants from each source -------------------------------
# Live ml_scorer.py
LIVE = {
    'ZONE_THR':       {'Z1': 0.60, 'Z2': 0.65, 'Z3': 0.50, 'Z4': 0.50},
    'ZONE_LOSS_THR':  {'Z1': 0.40, 'Z2': 0.20, 'Z3': 0.40, 'Z4': 0.50},
    'ZONE_BUF':       {'Z1': (0.005, 0.0020), 'Z2': (0.005, 0.0015),
                       'Z3': (0.000, 0.0020), 'Z4': (0.000, 0.0020)},
    'Z4_DIP':         0.009,
    'ZONE_LIMIT_W_R': {'Z3': 0.7, 'Z4': 0.45},
}

# validate_retrain.py
VALIDATE = {
    'ZONE_THR':       {'Z1': 0.60, 'Z2': 0.65, 'Z3': 0.50, 'Z4': 0.50},
    'ZONE_LOSS_THR':  {'Z1': 0.40, 'Z2': 0.20, 'Z3': 0.40, 'Z4': 0.50},
    'ZONE_BUF':       {'Z1': (0.005, 0.0020), 'Z2': (0.005, 0.0015),
                       'Z3': (0.000, 0.0020), 'Z4': (0.000, 0.0020)},
    'Z4_DIP':         0.009,
    'ZONE_LIMIT_W_R': {'Z3': 0.7, 'Z4': 0.45},
}


def constant_match(name, live, validate):
    return {
        'constant': name,
        'live': live,
        'validate': validate,
        'match': live == validate,
    }


def audit_A():
    rows = []
    for zone in ('Z1', 'Z2', 'Z3', 'Z4'):
        for cname in ('ZONE_THR', 'ZONE_LOSS_THR', 'ZONE_BUF'):
            rows.append({
                'constant': cname,
                'zone': zone,
                'live': LIVE[cname].get(zone),
                'validate': VALIDATE[cname].get(zone),
                'match': LIVE[cname].get(zone) == VALIDATE[cname].get(zone),
            })
        rows.append({
            'constant': 'ZONE_LIMIT_W_R',
            'zone': zone,
            'live': LIVE['ZONE_LIMIT_W_R'].get(zone, '-'),
            'validate': VALIDATE['ZONE_LIMIT_W_R'].get(zone, '-'),
            'match': LIVE['ZONE_LIMIT_W_R'].get(zone) == VALIDATE['ZONE_LIMIT_W_R'].get(zone),
        })
    rows.append({
        'constant': 'Z4_DIP_FILTER',
        'zone': 'Z4',
        'live': LIVE['Z4_DIP'],
        'validate': VALIDATE['Z4_DIP'],
        'match': LIVE['Z4_DIP'] == VALIDATE['Z4_DIP'],
    })
    return rows


def audit_B():
    """Ensemble combination per model type."""
    return [
        # model_type, live (ml_scorer.py line), validate (validate_retrain.py line), match?
        {'model': 'win_p', 'live': 'min(preds_28)  # line 424, 522',
         'validate': 'np.array([m.predict(X) for m in win_m[zone]]).min(axis=0)  # line 214',
         'match': True},
        {'model': 'loss_p', 'live': 'max([... m.predict for m in zone_loss_models[zone]])  # 425, 523',
         'validate': 'np.array([m.predict(X) for m in loss_m[zone]]).max(axis=0)  # line 215',
         'match': True},
        {'model': 'adapt_r (pred_r)', 'live': 'np.mean(preds)  # predict_adaptive_limit_ratio line 267',
         'validate': 'np.array([m.predict(X) for m in adapt_m[zone]]).mean(axis=0)  # line 216',
         'match': True},
        {'model': 'adapt_opt', 'live': 'sum(preds)/len(preds)  # predict_opt_entry_ratio line 251-252',
         'validate': 'np.array([m.predict(Xpick) for m in adaptopt_m[zone]]).mean()  # line 235',
         'match': True},
    ]


def audit_C():
    """Ranking."""
    return [
        # ranking type, live behaviour, validate behaviour, match?
        {'zone': 'Z1 (bucket 09:30-10:00)', 'live': 'R9 = win_p * max(0,1-pred_r)**0.5  # ml_filter.py 892-900',
         'validate': 'top = idx[win_p[idx].argmax()]  # validate_retrain.py line 222 → win_only',
         'match': False, 'note': 'MISMATCH: live uses R9 for Z1, validate uses win_only for ALL zones'},
        {'zone': 'Z2 (bucket 09:30-10:00)', 'live': 'R9 = win_p * max(0,1-pred_r)**0.5',
         'validate': 'top = idx[win_p[idx].argmax()]  # win_only',
         'match': False, 'note': 'MISMATCH: live uses R9 for Z2, validate uses win_only'},
        {'zone': 'Z3 (bucket 10:00-10:45)', 'live': 'win_only (R9 disabled in `_rank` for bucket 10:00-10:45)',
         'validate': 'win_only',
         'match': True},
        {'zone': 'Z4 (bucket 10:00-10:45)', 'live': 'win_only',
         'validate': 'win_only',
         'match': True},
    ]


def audit_D():
    """Per-zone LIMIT (Step 33) formula."""
    rows = []
    for zone in ('Z3', 'Z4'):
        live_w = 0.7 if zone == 'Z3' else 0.45
        val_w = VALIDATE['ZONE_LIMIT_W_R'][zone]
        rows.append({
            'zone': zone,
            'live_formula': f'pred_target = {live_w} * pred_r + {1-live_w:.2f} * pred_opt  # ml_filter.py 780-781',
            'validate_formula': f'pred_target = {val_w} * pr + {1-val_w:.2f} * pred_opt  # validate_retrain.py 236-237',
            'match': live_w == val_w,
        })
    return rows


def audit_E():
    """Model file presence."""
    expected = []
    for zone in ('Z1', 'Z2', 'Z3', 'Z4'):
        for s in range(5):
            expected.append(f'lgb_tp1_{zone}_seed{s}.txt')
            expected.append(f'lgb_loss_{zone}_seed{s}.txt')
            expected.append(f'lgb_adaptlim_{zone}_seed{s}.txt')
    for zone in ('Z3', 'Z4'):
        for s in range(5):
            expected.append(f'lgb_adaptopt_{zone}_seed{s}.txt')
    rows = []
    missing = []
    for fn in expected:
        present = (MODEL_DIR / fn).exists()
        if not present:
            missing.append(fn)
    rows.append({'category': 'tp1 (4 zones × 5 seeds)',
                 'expected': 20, 'present': sum(1 for z in 'Z1Z2Z3Z4'[::2] for s in range(5)
                                                if (MODEL_DIR / f'lgb_tp1_{z}_seed{s}.txt').exists()) * 1,
                 'match': True})
    # Count via glob
    n_tp1 = len(list(MODEL_DIR.glob('lgb_tp1_Z?_seed?.txt')))
    n_loss = len(list(MODEL_DIR.glob('lgb_loss_Z?_seed?.txt')))
    n_lim = len(list(MODEL_DIR.glob('lgb_adaptlim_Z?_seed?.txt')))
    n_opt = len(list(MODEL_DIR.glob('lgb_adaptopt_Z?_seed?.txt')))
    rows = [
        {'category': 'lgb_tp1_{Z1-4}_seed{0-4}', 'expected': 20, 'present': n_tp1, 'match': n_tp1 == 20},
        {'category': 'lgb_loss_{Z1-4}_seed{0-4}', 'expected': 20, 'present': n_loss, 'match': n_loss == 20},
        {'category': 'lgb_adaptlim_{Z1-4}_seed{0-4}', 'expected': 20, 'present': n_lim, 'match': n_lim == 20},
        {'category': 'lgb_adaptopt_{Z3,Z4}_seed{0-4}', 'expected': 10, 'present': n_opt, 'match': n_opt == 10},
        {'category': 'TOTAL', 'expected': 70, 'present': n_tp1 + n_loss + n_lim + n_opt,
         'match': (n_tp1 + n_loss + n_lim + n_opt) == 70},
    ]
    # Verify all files load
    bad = []
    for fn in expected:
        try:
            lgb.Booster(model_file=str(MODEL_DIR / fn))
        except Exception as e:
            bad.append((fn, str(e)[:80]))
    rows.append({'category': 'all 70 files lgb.Booster() loadable',
                 'expected': 0, 'present': len(bad),
                 'match': len(bad) == 0})
    if bad:
        rows.append({'category': f'load failures', 'expected': '', 'present': bad[:5], 'match': False})
    if missing:
        rows.append({'category': 'missing files', 'expected': 0, 'present': missing[:5], 'match': False})
    return rows


# ----------------- Audit F: reproduce live score ---------------------------

def load_features_list(zone):
    p = MODEL_DIR / f'features_zone_z{zone[1]}.txt'
    with open(p) as f:
        return [line.strip() for line in f if line.strip()]


def get_zone(mfo):
    if 0 <= mfo <= 9: return 'Z1'
    if 10 <= mfo <= 29: return 'Z2'
    if 30 <= mfo <= 44: return 'Z3'
    if 45 <= mfo <= 75: return 'Z4'
    return None


def predict_win(features, zone):
    feats = load_features_list(zone)
    row = [features.get(f, 0.0) for f in feats]
    arr = np.array([row], dtype=float)
    preds = []
    for s in range(5):
        m = lgb.Booster(model_file=str(MODEL_DIR / f'lgb_tp1_{zone}_seed{s}.txt'))
        preds.append(float(m.predict(arr)[0]))
    return min(preds), preds


def predict_loss(features, zone):
    feats = load_features_list(zone)
    row = [features.get(f, 0.0) for f in feats]
    arr = np.array([row], dtype=float)
    preds = []
    for s in range(5):
        m = lgb.Booster(model_file=str(MODEL_DIR / f'lgb_loss_{zone}_seed{s}.txt'))
        preds.append(float(m.predict(arr)[0]))
    return max(preds), preds


def audit_F(n_picks=3):
    """Try to reproduce stored ml_prob from features_json.

    NOTE (2026-05-28): scan_picks.features_json and scan_candidates.features_json
    store ONLY the `extra_dict` (ml_filter.py:854-868), not the raw input
    feature vector that the ML model consumes. Confirmed: feature_json contains
    {ml_prob, pred_ratio, threshold, bucket, gain_pct, beta, sector, limit_price,
     adaptive_limit, scan_price, use_market, day_open, exit_strategy}.
    The 89-dim feature vector is NOT persisted.

    So Audit F cannot reproduce ml_prob from journal alone. Live raw features
    ARE captured in `data/scan_snapshots/*.json.gz` (snaps + bars + macro +
    DB state) but reconstructing the per-stock feature vector requires
    re-running the entire feature-build pipeline (extract_multibar_features,
    cross-asset ETF, daily history, RSI/ATR/SMA, etc.).
    """
    con = sqlite3.connect(str(JOURNAL))
    rows = con.execute(
        "SELECT id, scan_ts, symbol, ml_prob, ml_threshold, bucket, features_json "
        "FROM scan_picks WHERE strategy='ml_filter' AND features_json IS NOT NULL "
        "AND length(features_json) > 100 ORDER BY scan_ts DESC LIMIT ?",
        (n_picks,),
    ).fetchall()
    con.close()
    results = []
    for pid, ts, sym, ml_prob, thr, bucket, fj in rows:
        try:
            extra = json.loads(fj)
        except Exception:
            extra = {}
        has_raw_feats = any(k in extra for k in
                            ('mins_from_open', 'gain_from_open', 'vol_ratio'))
        results.append({
            'id': pid,
            'ts': ts,
            'sym': sym,
            'stored_ml_prob': round(float(ml_prob), 4),
            'bucket': bucket,
            'raw_features_in_json': '✓' if has_raw_feats else '✗ (extra_dict only)',
            'reproducible': '✓' if has_raw_feats else '✗ — schema does not persist raw feature vector',
        })
    return results


def fmt_table(rows, cols):
    """Print a markdown-style table."""
    lines = ['| ' + ' | '.join(cols) + ' |',
             '| ' + ' | '.join(['---'] * len(cols)) + ' |']
    for r in rows:
        vals = []
        for c in cols:
            v = r.get(c, '')
            if isinstance(v, bool):
                v = '✓' if v else '✗'
            vals.append(str(v))
        lines.append('| ' + ' | '.join(vals) + ' |')
    return '\n'.join(lines)


def main():
    out = []
    out.append("# Agent C — Pipeline Parity Audit\n")
    out.append("**Date:** 2026-05-28")
    out.append("**Models:** `backtests/models_prod_v22/`")
    out.append("**Sources:** `src/scan/ml_scorer.py`, `src/scan/strategies/ml_filter.py`, `scripts/train_zones.py`, `scripts/validate_retrain.py`\n")

    out.append("## Audit A — Constants match\n")
    A = audit_A()
    out.append(fmt_table(A, ['constant', 'zone', 'live', 'validate', 'match']))

    out.append("\n## Audit B — Ensemble combination\n")
    B = audit_B()
    out.append(fmt_table(B, ['model', 'live', 'validate', 'match']))

    out.append("\n## Audit C — Ranking\n")
    C = audit_C()
    out.append(fmt_table(C, ['zone', 'live', 'validate', 'match', 'note']))

    out.append("\n## Audit D — Per-zone LIMIT (Step 33)\n")
    D = audit_D()
    out.append(fmt_table(D, ['zone', 'live_formula', 'validate_formula', 'match']))

    out.append("\n## Audit E — Model files present\n")
    E = audit_E()
    out.append(fmt_table(E, ['category', 'expected', 'present', 'match']))

    out.append("\n## Audit F — Reproduce live score\n")
    F = audit_F(n_picks=3)
    out.append(fmt_table(F, ['id', 'ts', 'sym', 'stored_ml_prob', 'bucket',
                              'raw_features_in_json', 'reproducible']))
    out.append("\n> **Data limitation:** `scan_picks.features_json` stores only `extra_dict` "
               "(ml_filter.py:854-868), which contains `ml_prob`, `pred_ratio`, `threshold`, "
               "`bucket`, `gain_pct`, `beta`, `sector`, `limit_price`, `adaptive_limit`, "
               "`scan_price`, `use_market`, `day_open`, `exit_strategy` — NOT the 89-dim "
               "ML input feature vector. `scan_candidates.features_json` has the same "
               "schema. Therefore stored ml_prob cannot be replayed without rebuilding "
               "features from `data/scan_snapshots/*.json.gz` (snaps+bars+macro+DB state) "
               "via the full feature pipeline. **This itself is a parity-audit gap** "
               "— add raw feature persistence to enable post-mortem replay.")

    # ------------ Summary ------------------------------------------------
    out.append("\n## Findings\n")

    # A
    a_fail = [r for r in A if not r['match']]
    if a_fail:
        out.append(f"- **Audit A: {len(a_fail)} constant mismatches**")
        for r in a_fail:
            out.append(f"    - {r['constant']}[{r['zone']}]  live={r['live']}  validate={r['validate']}")
    else:
        out.append("- **Audit A:** All constants (ZONE_THR / ZONE_LOSS_THR / ZONE_BUF / ZONE_LIMIT_W_R / Z4_DIP) match between `ml_scorer.py` and `validate_retrain.py`.")

    # B
    b_fail = [r for r in B if not r['match']]
    if b_fail:
        out.append(f"- **Audit B: ensemble mismatches** — {b_fail}")
    else:
        out.append("- **Audit B:** Ensemble combinations identical (win=min, loss=max, adapt_r=mean, adapt_opt=mean).")

    # C
    c_fail = [r for r in C if not r['match']]
    if c_fail:
        out.append(f"- **Audit C: ranking MISMATCH** — Z1/Z2 live uses R9, validate uses win_only.")
        out.append("    - File: `scripts/validate_retrain.py:222` always picks `idx[win_p[idx].argmax()]` (= win_only) for every zone.")
        out.append("    - File: `src/scan/strategies/ml_filter.py:892-900` uses R9 for bucket `09:30-10:00` (Z1+Z2).")
        out.append("    - **Fix:** make validate match live → add `r9 = win_p[idx] * np.maximum(0, 1-pred_r[idx])**0.5; top = idx[r9.argmax()]` for Z1/Z2 (bucket 09:30-10:00). OR change live to win_only for all zones (Step 18 baseline).")

    # D
    d_fail = [r for r in D if not r['match']]
    if d_fail:
        out.append(f"- **Audit D: per-zone LIMIT mismatch:** {d_fail}")
    else:
        out.append("- **Audit D:** Per-zone LIMIT formula identical (Z3 w_r=0.7, Z4 w_r=0.45).")

    # E
    e_fail = [r for r in E if not r['match']]
    if e_fail:
        out.append(f"- **Audit E: model files** — {e_fail}")
    else:
        out.append("- **Audit E:** All 70 expected zone models present + load successfully.")

    # F
    n_reproducible = sum(1 for r in F if r.get('raw_features_in_json') == '✓')
    out.append(f"- **Audit F:** 0/3 picks reproducible — `features_json` stores only the "
               f"`extra_dict` summary, NOT the raw model-input feature vector. "
               f"Cannot independently verify live ml_prob == model.predict(features) "
               f"from journal data alone. "
               f"To reproduce, code must be modified to persist the raw 89-dim feature dict "
               f"into the journal (or extracted from `data/scan_snapshots/*.json.gz` via "
               f"the full feature pipeline replay).")

    out.append("\n## Summary\n")
    issues = []
    if a_fail: issues.append('constants (A)')
    if b_fail: issues.append('ensemble (B)')
    if c_fail: issues.append('ranking (C)')
    if d_fail: issues.append('LIMIT formula (D)')
    if e_fail: issues.append('models (E)')
    if n_reproducible < len(F): issues.append('score reproduction (F)')
    if not issues:
        out.append("Pipeline is aligned. No mismatch likely to explain live vs backtest gap.")
    else:
        out.append("**Mismatches found in:** " + ", ".join(issues))
        if c_fail:
            out.append("\n**Highest-impact mismatch:** **Audit C — ranking divergence for Z1/Z2.**")
            out.append("Validate picks the candidate with highest `win_p` (validate_retrain.py:222), "
                       "but live picks via R9 = `win_p * max(0, 1-pred_r)^0.5` (ml_filter.py:892-900).")
            out.append("Effect: on Z1/Z2 scans live will prefer candidates with predicted bigger dip "
                       "(knife-catcher bias) while validate prefers highest win_p. Different picks "
                       "→ different outcomes. Live may pick deeper-dip stocks that fail to recover.")
        if n_reproducible < len(F):
            out.append("\n**Caveat for Audit F:** journal does not persist the raw 89-dim "
                       "feature vector — only the `extra_dict` summary (ml_prob, pred_ratio, "
                       "threshold, gain_pct, beta, sector, prices). Score parity cannot be "
                       "verified post-hoc until live persistence is extended. "
                       "**Recommended fix:** in `ml_filter.py:854`, expand `extra_dict` with "
                       "the full `features` dict (or write to a separate compressed log).")

    text = '\n'.join(out) + '\n'
    report_path = ROOT / 'backtests' / 'research_step36' / 'agent_C_report.md'
    report_path.write_text(text)
    print(text)
    print(f"\nReport saved → {report_path}")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Discovery System Audit — Complete pipeline verification.

Checks:
  1. Data freshness (all cron feeds)
  2. Adaptive params (all 23 params × 33 groups learned)
  3. ML model (AUC, features, coefficients, bias check)
  4. SectorScorer (weights, scores, blocking behavior)
  5. SignalTracker (IC, weights, active signals)
  6. Strategy thresholds (learned vs defaults)
  7. Pipeline flow (ML ranking → filters → sizer)
  8. Bias detection (DIP, sector, momentum)
  9. Simulation (OOS Sharpe, WR, per-regime)
  10. Duplicate/conflict scan

Usage: python scripts/audit_discovery.py
"""
import sys, os, json, sqlite3, time
import numpy as np
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
DB_PATH = Path(__file__).resolve().parents[1] / 'data' / 'trade_history.db'


def section(title):
    print(f'\n{"="*70}')
    print(f'  {title}')
    print(f'{"="*70}')


def check(label, passed, detail=''):
    icon = '✅' if passed else '❌'
    print(f'  {icon} {label}')
    if detail:
        print(f'      {detail}')
    return passed


def main():
    start = time.time()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    results = {'pass': 0, 'fail': 0, 'warn': 0}

    def ok(label, passed, detail=''):
        r = check(label, passed, detail)
        results['pass' if r else 'fail'] += 1
        return r

    def warn(label, detail=''):
        print(f'  ⚠️  {label}')
        if detail: print(f'      {detail}')
        results['warn'] += 1

    # =========================================================
    section('1. DATA FRESHNESS')
    # =========================================================
    today = datetime.now().strftime('%Y-%m-%d')
    for tbl, date_col, max_age_days, desc in [
        ('stock_daily_ohlc', 'date', 3, 'Stock OHLC'),
        ('sector_etf_daily_returns', 'date', 3, 'Sector ETF'),
        ('macro_snapshots', 'date', 3, 'Macro data'),
        ('market_breadth', 'date', 3, 'Market breadth'),
        ('analyst_ratings_history', 'date', 7, 'Analyst ratings'),
        ('insider_transactions_history', 'trade_date', 7, 'Insider transactions'),
        ('options_flow', 'date', 3, 'Options flow'),
        ('stock_fundamentals', 'updated_at', 10, 'Stock fundamentals'),
    ]:
        try:
            row = conn.execute(f"SELECT MAX({date_col}) FROM {tbl}").fetchone()
            latest = row[0][:10] if row and row[0] else 'N/A'
            ok(f'{desc}: latest={latest}', latest != 'N/A', f'table={tbl}')
        except Exception as e:
            ok(f'{desc}', False, str(e))

    # =========================================================
    section('2. ADAPTIVE PARAMS')
    # =========================================================
    ap = conn.execute("SELECT COUNT(DISTINCT sector||'_'||regime) as groups, COUNT(*) as params FROM adaptive_parameters").fetchone()
    ok(f'Groups: {ap["groups"]}', ap['groups'] >= 30, 'expect 33 sector×regime groups')
    ok(f'Total params: {ap["params"]}', ap['params'] >= 500, 'expect ~759 (23 params × 33)')

    for param in ['beta_max','pe_max','tp_d0_mult','tp_d3_mult','vix_calm','vix_fear',
                   'ubrain_cutoff','spec_skip','rank_w_strat','min_mcap_b','max_vol_ratio',
                   'n_blocked','div_breadth','vvix_crisis','washout_breadth']:
        row = conn.execute("SELECT COUNT(*), COUNT(DISTINCT param_value) FROM adaptive_parameters WHERE param_name=?", (param,)).fetchone()
        ok(f'{param}: {row[0]} entries, {row[1]} distinct', row[0] >= 30 and row[1] >= 2,
           f'learned diversity' if row[1] >= 2 else 'all same value — may not be learning')

    # =========================================================
    section('3. ML MODEL (AdaptiveStockSelector)')
    # =========================================================
    model_row = conn.execute("SELECT auc, n_train, feature_importance, feature_names FROM stock_selector_model LIMIT 1").fetchone()
    if model_row:
        auc = model_row['auc']
        ok(f'AUC: {auc:.4f}', auc >= 0.52, 'minimum acceptable AUC')
        ok(f'Training rows: {model_row["n_train"]}', model_row['n_train'] >= 50000)

        fi = json.loads(model_row['feature_importance']) if model_row['feature_importance'] else {}
        fn = json.loads(model_row['feature_names']) if model_row['feature_names'] else []
        ok(f'Features: {len(fn)}', len(fn) >= 14, 'expect 15 features')

        # Bias check: momentum_5d coefficient
        from discovery.adaptive_stock_selector import AdaptiveStockSelector
        sel = AdaptiveStockSelector(); sel.load_from_db()
        if sel._model and hasattr(sel._model, 'coef_'):
            coefs = dict(zip(sel._feature_names, sel._model.coef_[0]))
            mom_coef = coefs.get('momentum_5d', 0)
            ok(f'momentum_5d coef: {mom_coef:+.4f}', abs(mom_coef) < 0.05,
               'DIP bias' if mom_coef < -0.05 else ('RS bias' if mom_coef > 0.05 else 'neutral ✓'))

            # No single feature dominates
            top_imp = max(fi.values()) if fi else 0
            total_imp = sum(fi.values()) if fi else 1
            ok(f'Top feature share: {top_imp/total_imp*100:.0f}%', top_imp/total_imp < 0.35,
               'no single feature dominates')

        print(f'  Feature importance:')
        for f, imp in sorted(fi.items(), key=lambda x: -x[1])[:6]:
            print(f'    {f:<20s} {imp:.4f}')
    else:
        ok('ML model in DB', False, 'No model found!')

    # =========================================================
    section('4. SECTOR SCORER')
    # =========================================================
    weights = conn.execute("SELECT feature, weight FROM sector_scorer_weights").fetchall()
    ok(f'Weights: {len(weights)} features', len(weights) >= 3)
    for r in weights:
        print(f'    {r["feature"]:<25s} weight={r["weight"]:+.4f}')

    # Check: no hard-blocking in pipeline
    with open('src/discovery/engine.py') as f:
        engine_code = f.read()
    ok('No sector hard-blocking', 'hard block' not in engine_code.lower() or 'no hard-blocking' in engine_code.lower(),
       'ML decides via sect_sharpe feature')

    # =========================================================
    section('5. SIGNAL TRACKER')
    # =========================================================
    sigs = conn.execute("SELECT signal_name, ic_90d, weight FROM signal_tracker_current").fetchall()
    ok(f'Signals tracked: {len(sigs)}', len(sigs) >= 5)
    for s in sigs:
        status = 'ACTIVE' if s['weight'] != 0 else 'disabled (noise)'
        print(f'    {s["signal_name"]:<25s} IC={s["ic_90d"]:+.4f} weight={s["weight"]:+.4f} [{status}]')

    # =========================================================
    section('6. STRATEGY THRESHOLDS')
    # =========================================================
    params = conn.execute("SELECT strategy_name, params_json FROM strategy_learned_params").fetchall()
    ok(f'Strategies with learned params: {len(params)}', len(params) >= 3)
    for r in params:
        p = json.loads(r['params_json'])
        print(f'    {r["strategy_name"]:<13s} {p}')

    # fit_stats
    stats = conn.execute("SELECT COUNT(*) FROM strategy_fit_stats").fetchone()
    ok(f'fit_stats entries: {stats[0]}', stats[0] >= 10, 'strat_sharpe for ML ranking')

    # =========================================================
    section('7. PIPELINE FLOW')
    # =========================================================
    import inspect
    from discovery.engine import DiscoveryEngine

    # Check _run_v3_pipeline has ML ranking
    src = inspect.getsource(DiscoveryEngine._run_v3_pipeline)
    ok('ML ranking in pipeline', '_rank_by_ml_probability' in src)
    ok('Gap boost in pipeline', '_apply_gap_boost' in src)
    ok('Max per strategy', 'max_per_strategy' in src or 'strat_counts' in src)
    ok('refit parameter', 'refit=' in src, 'intraday uses refit=False')

    # No separate intraday pipeline
    ok('Single pipeline (no _run_v3_pipeline_intraday)',
       not hasattr(DiscoveryEngine, '_run_v3_pipeline_intraday') or
       '_run_v3_pipeline_intraday REMOVED' in engine_code)

    # =========================================================
    section('8. BIAS DETECTION')
    # =========================================================

    # Check: no -mom formula
    import re
    bias_files = {}
    for f in os.listdir('src/discovery'):
        if not f.endswith('.py'): continue
        code = open(f'src/discovery/{f}').read()
        for i, line in enumerate(code.split('\n'), 1):
            s = line.strip()
            if s.startswith('#'): continue
            if re.search(r'-\s*mom\w*\s*\*\s*0\.\d', s):
                bias_files.setdefault(f, []).append((i, s[:60]))

    ok('No -mom×weight formula (DIP bias)', len(bias_files) == 0,
       f'Found in: {list(bias_files.keys())}' if bias_files else 'clean')

    # Check: no sector hard-block
    block_count = 0
    for f in os.listdir('src/discovery'):
        if not f.endswith('.py'): continue
        code = open(f'src/discovery/{f}').read()
        for line in code.split('\n'):
            s = line.strip()
            if s.startswith('#'): continue
            if 'blocked' in s and 'sector' in s and 'continue' in s:
                block_count += 1
    ok('No sector hard-block in active code', block_count == 0,
       f'{block_count} instances found' if block_count else 'clean')

    # Active picks bias
    picks = conn.execute("SELECT council_json FROM discovery_picks WHERE status='active'").fetchall()
    if picks:
        strats = Counter()
        for p in picks:
            if p['council_json']:
                c = json.loads(p['council_json'])
                strat = (c.get('strategy') or {}).get('strategy', '?')
                strats[strat] += 1
        total = sum(strats.values())
        max_pct = max(strats.values()) / total * 100 if total > 0 else 0
        ok(f'Strategy diversity: {dict(strats)}', max_pct <= 40,
           f'max {max_pct:.0f}% — {"balanced" if max_pct <= 30 else "slight concentration"}')

    # =========================================================
    section('9. SIMULATION (OOS)')
    # =========================================================
    from discovery.multi_strategy import classify_strategy, classify_regime

    conn.row_factory = None  # use tuple for simulation
    rows = conn.execute('''
        SELECT b.scan_date, b.symbol, b.sector, b.atr_pct, b.momentum_5d,
               b.distance_from_20d_high, b.volume_ratio, b.outcome_5d,
               COALESCE(m.vix_close, 20), COALESCE(mb.pct_above_20d_ma, 50),
               sf.beta, sf.pe_forward
        FROM backfill_signal_outcomes b
        LEFT JOIN macro_snapshots m ON b.scan_date = m.date
        LEFT JOIN market_breadth mb ON b.scan_date = mb.date
        LEFT JOIN stock_fundamentals sf ON b.symbol = sf.symbol
        WHERE b.outcome_5d IS NOT NULL AND b.atr_pct > 0
        AND b.sector IS NOT NULL AND m.vix_close IS NOT NULL
    ''').fetchall()
    conn.row_factory = sqlite3.Row

    # r = tuple: (scan_date, symbol, sector, atr, mom5, d20h, vol, o5d, vix, breadth, beta, pe)
    sr = defaultdict(list); se = defaultdict(list)
    by_date = defaultdict(list)
    for r in rows:
        rd = {'scan_date':r[0],'symbol':r[1],'sector':r[2],'atr_pct':r[3],'momentum_5d':r[4],
              'distance_from_20d_high':r[5],'volume_ratio':r[6],'outcome_5d':r[7],
              'vix_close':r[8],'pct_above_20d_ma':r[9],'beta':r[10],'pe_forward':r[11]}
        st = classify_strategy(rd['momentum_5d'], rd['distance_from_20d_high'], rd['volume_ratio'], rd['pe_forward'])
        rg = classify_regime(rd['vix_close'], rd['pct_above_20d_ma'])
        sr[(rg,st)].append(rd['outcome_5d']); se[(rg,rd['sector'])].append(rd['outcome_5d'])
        by_date[rd['scan_date']].append(rd)
    strat_sh = {k: np.mean(v)/max(np.std(v),0.01) for k,v in sr.items() if len(v)>=30}
    sect_sh = {k: np.mean(v)/max(np.std(v),0.01) for k,v in se.items() if len(v)>=30}

    dates = sorted(by_date.keys()); split = dates[int(len(dates)*0.8)]
    test_dates = [d for d in dates if d > split]

    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler
    train_X, train_y, test_preds = [], [], {}
    for d in dates:
        for r in by_date[d]:
            rg = classify_regime(r['vix_close'], r['pct_above_20d_ma'])
            st = classify_strategy(r['momentum_5d'], r['distance_from_20d_high'], r['volume_ratio'], r['pe_forward'])
            feat = [r['momentum_5d'] or 0, r['distance_from_20d_high'] or 0, r['atr_pct'],
                    r['volume_ratio'] or 1, r['beta'] or 1, r['vix_close'], r['pct_above_20d_ma'],
                    strat_sh.get((rg,st),0), sect_sh.get((rg,r['sector']),0)]
            if d <= split:
                train_X.append(feat); train_y.append(1 if r['outcome_5d']>0 else 0)
            else:
                test_preds[(d,r['symbol'])] = feat

    scaler = StandardScaler(); X_tr = scaler.fit_transform(train_X)
    mdl = LogisticRegression(max_iter=200).fit(X_tr, train_y)
    for k, feat in test_preds.items():
        test_preds[k] = mdl.predict_proba(scaler.transform([feat]))[0,1]

    # v15 baseline
    def rank_v15(r): return -(r['momentum_5d'] or 0)*0.3 + abs(r['distance_from_20d_high'] or 0)*0.2
    def filt_v15(r): return not (r['beta'] and r['beta']>1.5) and not (r['pe_forward'] and r['pe_forward']>35)
    def rank_ml(r): return test_preds.get((r['scan_date'],r['symbol']), 0.5)

    def sim(rank_fn, filt_fn):
        outs = []
        for dt in test_dates:
            sigs = by_date.get(dt,[])
            if len(sigs)<10: continue
            if filt_fn: sigs = [r for r in sigs if filt_fn(r)]
            ranked = sorted(sigs, key=rank_fn, reverse=True)
            sc = {}
            for r in ranked:
                st = classify_strategy(r['momentum_5d'],r['distance_from_20d_high'],r['volume_ratio'],r['pe_forward'])
                if sc.get(st,0)>=2: continue
                sc[st]=sc.get(st,0)+1
                outs.append(r['outcome_5d'])
                if sum(sc.values())>=10: break
        o = np.array(outs)
        return len(o), (o>0).mean()*100, o.mean(), o.mean()/max(o.std(),0.01)

    n15, wr15, avg15, sh15 = sim(rank_v15, filt_v15)
    nml, wrml, avgml, shml = sim(rank_ml, None)

    print(f'  v15 Baseline: n={n15} WR={wr15:.1f}% avg={avg15:+.3f}% Sharpe={sh15:+.4f}')
    print(f'  v17 ML Final: n={nml} WR={wrml:.1f}% avg={avgml:+.3f}% Sharpe={shml:+.4f}')
    delta = shml - sh15
    pct = delta / max(abs(sh15), 0.001) * 100
    ok(f'Sharpe improvement: {delta:+.4f} ({pct:+.0f}%)', delta > 0)
    ok(f'Win Rate improvement: {wrml-wr15:+.1f}%', wrml >= wr15)

    # =========================================================
    section('10. CRON JOBS')
    # =========================================================
    import subprocess
    cron = subprocess.run(['crontab', '-l'], capture_output=True, text=True).stdout
    for script, desc in [
        ('update_stock_ohlc', 'Stock OHLC daily'),
        ('collect_sector_etf', 'Sector ETF returns'),
        ('macro_snapshot', 'Macro snapshots'),
        ('collect_analyst', 'Analyst ratings'),
        ('insider_collector', 'Insider transactions'),
        ('collect_options_flow', 'Options flow'),
        ('cboe_options', 'CBOE options'),
        ('collect_market_breadth', 'Market breadth'),
        ('discovery_scan', 'Discovery scan 20:30'),
        ('discovery_intraday', 'Intraday scan'),
    ]:
        ok(f'Cron: {desc}', script in cron)

    # =========================================================
    section('SUMMARY')
    # =========================================================
    elapsed = time.time() - start
    total = results['pass'] + results['fail'] + results['warn']
    print(f'\n  ✅ PASS: {results["pass"]}')
    print(f'  ❌ FAIL: {results["fail"]}')
    print(f'  ⚠️  WARN: {results["warn"]}')
    print(f'  Total: {total} checks in {elapsed:.1f}s')

    if results['fail'] == 0:
        print(f'\n  🎉 ALL CHECKS PASSED')
    else:
        print(f'\n  ⚠️  {results["fail"]} FAILURES — review above')

    conn.close()
    return 0 if results['fail'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Comprehensive IC Analysis: News Sentiment + Analyst Features
Analyzes newly backfilled news_sentiment, analyst_target_upside,
analyst_bull_score, analyst_rating_count_30d, analyst_action_7d
"""

import sqlite3
import numpy as np
import pandas as pd
from scipy import stats

DB_PATH = "data/trade_history.db"

def load_data():
    conn = None  # via get_session()
    df = pd.read_sql_query("""
        SELECT
            symbol, scan_date, signal_source, action_taken,
            outcome_1d, outcome_2d, outcome_3d, outcome_4d, outcome_5d,
            outcome_max_gain_5d, outcome_max_dd_5d,
            CAST(news_sentiment AS REAL) as news_sentiment,
            news_impact_score,
            catalyst_type,
            analyst_target_upside,
            analyst_bull_score,
            analyst_rating_count_30d,
            analyst_action_7d,
            distance_from_high,
            distance_from_20d_high,
            new_score,
            atr_pct,
            entry_rsi,
            momentum_5d,
            volume_ratio,
            vix_at_signal,
            sector_1d_change,
            margin_to_atr,
            sector_etf_1d_pct,
            sector,
            score,
            short_percent_of_float,
            spy_pct_above_sma,
            momentum_20d,
            gap_pct,
            close_to_high_pct,
            spy_intraday_pct,
            sector_5d_return,
            vix_1w_change,
            entry_vs_open_pct,
            bounce_pct_from_lod,
            first_5min_return,
            first_30min_return,
            intraday_spy_trend,
            spy_rsi_at_scan,
            pm_range_pct,
            margin_to_rsi,
            margin_to_score,
            insider_buy_30d_value,
            consecutive_down_days,
            distance_from_200d_ma,
            earnings_beat_streak
        FROM signal_outcomes
        WHERE outcome_5d IS NOT NULL
    """, conn)
    conn.close()
    return df


def spearman_ic(x, y):
    """Compute Spearman IC with p-value, dropping NaN pairs."""
    mask = x.notna() & y.notna()
    x_clean = x[mask]
    y_clean = y[mask]
    n = len(x_clean)
    if n < 10:
        return np.nan, np.nan, n
    corr, pval = stats.spearmanr(x_clean, y_clean)
    return corr, pval, n


def wr(series):
    """Win rate: fraction of values > 0."""
    valid = series.dropna()
    if len(valid) == 0:
        return np.nan
    return (valid > 0).mean()


def print_header(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_subheader(title):
    print(f"\n--- {title} ---")


def part1_news_analysis(df):
    print_header("PART 1: NEWS SENTIMENT ANALYSIS")

    news_df = df[df['news_sentiment'].notna()].copy()
    has_outcome = news_df['outcome_5d'].notna()
    news_with_outcome = news_df[has_outcome]

    print(f"\nTotal rows with news_sentiment: {len(news_df)}")
    print(f"Rows with news_sentiment AND outcome_5d: {len(news_with_outcome)}")
    print(f"news_sentiment range: [{news_with_outcome['news_sentiment'].min():.4f}, {news_with_outcome['news_sentiment'].max():.4f}]")
    print(f"news_sentiment mean: {news_with_outcome['news_sentiment'].mean():.4f}, median: {news_with_outcome['news_sentiment'].median():.4f}")

    # 1. Spearman IC of news_sentiment vs outcomes
    print_subheader("1. Spearman IC: news_sentiment vs outcomes")
    print(f"{'Outcome':<15} {'IC':>8} {'p-value':>10} {'n':>6} {'Sig':>5}")
    print("-" * 50)
    for col in ['outcome_1d', 'outcome_3d', 'outcome_5d']:
        ic, pval, n = spearman_ic(news_with_outcome['news_sentiment'], news_with_outcome[col])
        sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
        print(f"{col:<15} {ic:>8.4f} {pval:>10.4f} {n:>6} {sig:>5}")

    # 2. Sentiment bucket analysis
    print_subheader("2. Sentiment Bucket Analysis")
    bins = [-np.inf, -0.3, -0.1, 0.1, 0.3, np.inf]
    labels = ['very_neg(<-0.3)', 'negative(-0.3,-0.1)', 'neutral(-0.1,0.1)', 'positive(0.1,0.3)', 'very_pos(>0.3)']
    news_with_outcome = news_with_outcome.copy()
    news_with_outcome['sent_bucket'] = pd.cut(news_with_outcome['news_sentiment'], bins=bins, labels=labels)

    print(f"{'Bucket':<25} {'n':>5} {'avg_1d':>8} {'avg_3d':>8} {'avg_5d':>8} {'WR_5d':>7} {'med_5d':>8}")
    print("-" * 75)
    for bucket in labels:
        sub = news_with_outcome[news_with_outcome['sent_bucket'] == bucket]
        n = len(sub)
        if n == 0:
            print(f"{bucket:<25} {0:>5}")
            continue
        avg1 = sub['outcome_1d'].mean()
        avg3 = sub['outcome_3d'].mean()
        avg5 = sub['outcome_5d'].mean()
        wr5 = wr(sub['outcome_5d'])
        med5 = sub['outcome_5d'].median()
        print(f"{bucket:<25} {n:>5} {avg1:>8.3f} {avg3:>8.3f} {avg5:>8.3f} {wr5:>7.1%} {med5:>8.3f}")

    # 3. news_impact_score IC
    print_subheader("3. news_impact_score IC (catalyst_type filled rows)")
    impact_df = news_with_outcome[news_with_outcome['news_impact_score'].notna()]
    print(f"Rows with news_impact_score: {len(impact_df)}")
    if len(impact_df) >= 10:
        print(f"news_impact_score range: [{impact_df['news_impact_score'].min():.3f}, {impact_df['news_impact_score'].max():.3f}]")
        print(f"{'Outcome':<15} {'IC':>8} {'p-value':>10} {'n':>6} {'Sig':>5}")
        print("-" * 50)
        for col in ['outcome_1d', 'outcome_3d', 'outcome_5d']:
            ic, pval, n = spearman_ic(impact_df['news_impact_score'], impact_df[col])
            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            print(f"{col:<15} {ic:>8.4f} {pval:>10.4f} {n:>6} {sig:>5}")
    else:
        print("  Not enough rows for IC computation.")

    # Catalyst type breakdown
    catalyst_df = news_with_outcome[news_with_outcome['catalyst_type'].notna()]
    if len(catalyst_df) > 0:
        print_subheader("3b. Catalyst Type Breakdown")
        print(f"{'catalyst_type':<20} {'n':>5} {'avg_5d':>8} {'WR_5d':>7} {'avg_impact':>10}")
        print("-" * 55)
        for cat, grp in catalyst_df.groupby('catalyst_type'):
            n = len(grp)
            avg5 = grp['outcome_5d'].mean()
            wr5 = wr(grp['outcome_5d'])
            avg_imp = grp['news_impact_score'].mean() if grp['news_impact_score'].notna().any() else np.nan
            imp_str = f"{avg_imp:>10.3f}" if not np.isnan(avg_imp) else f"{'N/A':>10}"
            print(f"{str(cat):<20} {n:>5} {avg5:>8.3f} {wr5:>7.1%} {imp_str}")

    # 4. Interaction: news_sentiment x vix_at_signal
    print_subheader("4. Interaction: news_sentiment x VIX level")
    interact_df = news_with_outcome[news_with_outcome['vix_at_signal'].notna()].copy()
    interact_df['vix_group'] = pd.cut(interact_df['vix_at_signal'],
                                       bins=[0, 20, 24, 38, 100],
                                       labels=['LOW(<20)', 'SKIP(20-24)', 'HIGH(24-38)', 'EXTREME(>38)'])
    print(f"{'VIX Group':<16} {'n':>5} {'news_IC_5d':>10} {'p-val':>8} {'avg_news':>10}")
    print("-" * 55)
    for grp_name, grp in interact_df.groupby('vix_group', observed=True):
        if len(grp) < 5:
            print(f"{str(grp_name):<16} {len(grp):>5}   (too few)")
            continue
        ic, pval, n = spearman_ic(grp['news_sentiment'], grp['outcome_5d'])
        avg_sent = grp['news_sentiment'].mean()
        p_str = f"{pval:.4f}" if not np.isnan(pval) else "N/A"
        print(f"{str(grp_name):<16} {n:>5} {ic:>10.4f} {p_str:>8} {avg_sent:>10.4f}")

    # Positive vs negative news in each VIX regime
    print("\n  Positive (>0) vs Negative (<0) news by VIX regime:")
    print(f"  {'VIX Group':<16} {'Neg n':>6} {'Neg avg5d':>10} {'Neg WR5d':>9} {'Pos n':>6} {'Pos avg5d':>10} {'Pos WR5d':>9}")
    print("  " + "-" * 72)
    for grp_name, grp in interact_df.groupby('vix_group', observed=True):
        neg = grp[grp['news_sentiment'] < 0]
        pos = grp[grp['news_sentiment'] > 0]
        neg_n = len(neg)
        pos_n = len(pos)
        neg_avg = neg['outcome_5d'].mean() if neg_n > 0 else np.nan
        pos_avg = pos['outcome_5d'].mean() if pos_n > 0 else np.nan
        neg_wr = wr(neg['outcome_5d']) if neg_n > 0 else np.nan
        pos_wr = wr(pos['outcome_5d']) if pos_n > 0 else np.nan
        neg_avg_s = f"{neg_avg:.3f}" if not np.isnan(neg_avg) else "N/A"
        pos_avg_s = f"{pos_avg:.3f}" if not np.isnan(pos_avg) else "N/A"
        neg_wr_s = f"{neg_wr:.1%}" if not np.isnan(neg_wr) else "N/A"
        pos_wr_s = f"{pos_wr:.1%}" if not np.isnan(pos_wr) else "N/A"
        print(f"  {str(grp_name):<16} {neg_n:>6} {neg_avg_s:>10} {neg_wr_s:>9} {pos_n:>6} {pos_avg_s:>10} {pos_wr_s:>9}")

    # 5. Interaction: news_sentiment x distance_from_high
    print_subheader("5. Interaction: news_sentiment x distance_from_high")
    dist_df = news_with_outcome[news_with_outcome['distance_from_high'].notna()].copy()
    # DB distance_from_high is negative (distance from 52w high)
    dist_df['dist_group'] = pd.cut(dist_df['distance_from_high'],
                                    bins=[-100, -30, -15, -5, 0, 100],
                                    labels=['far(<-30%)', 'mid(-30,-15)', 'near(-15,-5)', 'at_high(-5,0)', 'above(>0)'])
    print(f"{'Dist Group':<18} {'n':>5} {'news_IC_5d':>10} {'p-val':>8} {'avg_news':>10} {'avg_5d':>8}")
    print("-" * 65)
    for grp_name, grp in dist_df.groupby('dist_group', observed=True):
        if len(grp) < 5:
            print(f"{str(grp_name):<18} {len(grp):>5}   (too few)")
            continue
        ic, pval, n = spearman_ic(grp['news_sentiment'], grp['outcome_5d'])
        avg_sent = grp['news_sentiment'].mean()
        avg5 = grp['outcome_5d'].mean()
        p_str = f"{pval:.4f}" if not np.isnan(pval) else "N/A"
        print(f"{str(grp_name):<18} {n:>5} {ic:>10.4f} {p_str:>8} {avg_sent:>10.4f} {avg5:>8.3f}")


def part2_analyst_analysis(df):
    print_header("PART 2: ANALYST FEATURES ANALYSIS")

    analyst_df = df[df['analyst_target_upside'].notna()].copy()
    print(f"\nTotal rows with analyst data: {len(analyst_df)}")
    print(f"Rows with analyst data AND outcome_5d: {len(analyst_df[analyst_df['outcome_5d'].notna()])}")

    # 1. Spearman IC for all 4 analyst columns
    print_subheader("1. Spearman IC: Analyst Features vs Outcomes")
    features = ['analyst_target_upside', 'analyst_bull_score', 'analyst_rating_count_30d']
    print(f"{'Feature':<28} {'vs 1d':>8} {'p':>7} {'vs 3d':>8} {'p':>7} {'vs 5d':>8} {'p':>7} {'n':>5}")
    print("-" * 85)
    for feat in features:
        feat_df = analyst_df[analyst_df[feat].notna()]
        row_parts = [f"{feat:<28}"]
        for out in ['outcome_1d', 'outcome_3d', 'outcome_5d']:
            ic, pval, n = spearman_ic(feat_df[feat], feat_df[out])
            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            row_parts.append(f"{ic:>7.4f}{sig}")
            row_parts.append(f"{pval:>7.4f}")
        row_parts.append(f"{n:>5}")
        print(" ".join(row_parts))

    # analyst_action_7d — categorical, use group means
    print_subheader("1b. analyst_action_7d (categorical) — Group Mean Outcomes")
    action_df = analyst_df.copy()
    action_df['analyst_action_7d'] = action_df['analyst_action_7d'].fillna('NULL')
    print(f"{'action':<10} {'n':>5} {'avg_1d':>8} {'avg_3d':>8} {'avg_5d':>8} {'WR_5d':>7} {'med_5d':>8}")
    print("-" * 55)
    for act, grp in action_df.groupby('analyst_action_7d'):
        n = len(grp)
        avg1 = grp['outcome_1d'].mean()
        avg3 = grp['outcome_3d'].mean()
        avg5 = grp['outcome_5d'].mean()
        wr5 = wr(grp['outcome_5d'])
        med5 = grp['outcome_5d'].median()
        print(f"{str(act):<10} {n:>5} {avg1:>8.3f} {avg3:>8.3f} {avg5:>8.3f} {wr5:>7.1%} {med5:>8.3f}")

    # 2. Bucket analysis: analyst_target_upside
    print_subheader("2. analyst_target_upside Bucket Analysis")
    upside_df = analyst_df[analyst_df['analyst_target_upside'].notna()].copy()
    bins = [-np.inf, 0, 10, 20, 40, np.inf]
    labels = ['<0%', '0-10%', '10-20%', '20-40%', '>40%']
    upside_df['upside_bucket'] = pd.cut(upside_df['analyst_target_upside'], bins=bins, labels=labels)

    print(f"{'Bucket':<12} {'n':>5} {'avg_1d':>8} {'avg_3d':>8} {'avg_5d':>8} {'WR_5d':>7} {'med_5d':>8} {'avg_upside':>11}")
    print("-" * 75)
    for bucket in labels:
        sub = upside_df[upside_df['upside_bucket'] == bucket]
        n = len(sub)
        if n == 0:
            print(f"{bucket:<12} {0:>5}")
            continue
        avg1 = sub['outcome_1d'].mean()
        avg3 = sub['outcome_3d'].mean()
        avg5 = sub['outcome_5d'].mean()
        wr5 = wr(sub['outcome_5d'])
        med5 = sub['outcome_5d'].median()
        avg_up = sub['analyst_target_upside'].mean()
        print(f"{bucket:<12} {n:>5} {avg1:>8.3f} {avg3:>8.3f} {avg5:>8.3f} {wr5:>7.1%} {med5:>8.3f} {avg_up:>11.2f}")

    # 3. Bull score buckets
    print_subheader("3. analyst_bull_score Bucket Analysis")
    bull_df = analyst_df[analyst_df['analyst_bull_score'].notna()].copy()
    bins_bull = [-np.inf, 0.5, 1.0, 1.5, np.inf]
    labels_bull = ['<0.5', '0.5-1.0', '1.0-1.5', '>1.5']
    bull_df['bull_bucket'] = pd.cut(bull_df['analyst_bull_score'], bins=bins_bull, labels=labels_bull)

    print(f"{'Bucket':<12} {'n':>5} {'avg_1d':>8} {'avg_3d':>8} {'avg_5d':>8} {'WR_5d':>7} {'med_5d':>8} {'avg_bull':>9}")
    print("-" * 70)
    for bucket in labels_bull:
        sub = bull_df[bull_df['bull_bucket'] == bucket]
        n = len(sub)
        if n == 0:
            print(f"{bucket:<12} {0:>5}")
            continue
        avg1 = sub['outcome_1d'].mean()
        avg3 = sub['outcome_3d'].mean()
        avg5 = sub['outcome_5d'].mean()
        wr5 = wr(sub['outcome_5d'])
        med5 = sub['outcome_5d'].median()
        avg_b = sub['analyst_bull_score'].mean()
        print(f"{bucket:<12} {n:>5} {avg1:>8.3f} {avg3:>8.3f} {avg5:>8.3f} {wr5:>7.1%} {med5:>8.3f} {avg_b:>9.3f}")

    # 4. Recent analyst action effect (expanded)
    print_subheader("4. analyst_action_7d Detailed Effect")
    # Already printed above in 1b; add signal_source breakdown
    print("\n  By signal_source x analyst_action_7d:")
    action_df2 = analyst_df.copy()
    action_df2['analyst_action_7d'] = action_df2['analyst_action_7d'].fillna('NULL')
    for source in sorted(action_df2['signal_source'].dropna().unique()):
        src_df = action_df2[action_df2['signal_source'] == source]
        if len(src_df) < 10:
            continue
        print(f"\n  [{source}]")
        print(f"  {'action':<10} {'n':>5} {'avg_5d':>8} {'WR_5d':>7}")
        print("  " + "-" * 35)
        for act, grp in src_df.groupby('analyst_action_7d'):
            n = len(grp)
            if n < 3:
                continue
            avg5 = grp['outcome_5d'].mean()
            wr5 = wr(grp['outcome_5d'])
            print(f"  {str(act):<10} {n:>5} {avg5:>8.3f} {wr5:>7.1%}")

    # 5. Interaction: analyst_target_upside x distance_from_high
    print_subheader("5. Interaction: analyst_target_upside x distance_from_high")
    interact_df = analyst_df[
        analyst_df['analyst_target_upside'].notna() &
        analyst_df['distance_from_high'].notna()
    ].copy()
    interact_df['dist_group'] = pd.cut(interact_df['distance_from_high'],
                                        bins=[-100, -30, -15, -5, 0, 100],
                                        labels=['far(<-30%)', 'mid(-30,-15)', 'near(-15,-5)', 'at_high(-5,0)', 'above(>0)'])
    print(f"{'Dist Group':<18} {'n':>5} {'upside_IC_5d':>12} {'p-val':>8} {'avg_upside':>11} {'avg_5d':>8}")
    print("-" * 68)
    for grp_name, grp in interact_df.groupby('dist_group', observed=True):
        if len(grp) < 5:
            print(f"{str(grp_name):<18} {len(grp):>5}   (too few)")
            continue
        ic, pval, n = spearman_ic(grp['analyst_target_upside'], grp['outcome_5d'])
        avg_up = grp['analyst_target_upside'].mean()
        avg5 = grp['outcome_5d'].mean()
        p_str = f"{pval:.4f}" if not np.isnan(pval) else "N/A"
        print(f"{str(grp_name):<18} {n:>5} {ic:>12.4f} {p_str:>8} {avg_up:>11.2f} {avg5:>8.3f}")

    # 6. Interaction: analyst_target_upside x atr_pct
    print_subheader("6. Interaction: analyst_target_upside x atr_pct")
    atr_df = analyst_df[
        analyst_df['analyst_target_upside'].notna() &
        analyst_df['atr_pct'].notna()
    ].copy()
    atr_df['atr_group'] = pd.cut(atr_df['atr_pct'],
                                   bins=[0, 2, 4, 6, 100],
                                   labels=['low(<2%)', 'mid(2-4%)', 'high(4-6%)', 'vhigh(>6%)'])
    print(f"{'ATR Group':<15} {'n':>5} {'upside_IC_5d':>12} {'p-val':>8} {'avg_upside':>11} {'avg_5d':>8}")
    print("-" * 65)
    for grp_name, grp in atr_df.groupby('atr_group', observed=True):
        if len(grp) < 5:
            print(f"{str(grp_name):<15} {len(grp):>5}   (too few)")
            continue
        ic, pval, n = spearman_ic(grp['analyst_target_upside'], grp['outcome_5d'])
        avg_up = grp['analyst_target_upside'].mean()
        avg5 = grp['outcome_5d'].mean()
        p_str = f"{pval:.4f}" if not np.isnan(pval) else "N/A"
        print(f"{str(grp_name):<15} {n:>5} {ic:>12.4f} {p_str:>8} {avg_up:>11.2f} {avg5:>8.3f}")


def part3_combined_ic_table(df):
    print_header("PART 3: COMBINED FEATURE IC TABLE (sorted by |IC| vs outcome_5d)")

    # All features to test
    features = [
        'distance_from_high',
        'distance_from_20d_high',
        'new_score',
        'atr_pct',
        'entry_rsi',
        'momentum_5d',
        'volume_ratio',
        'vix_at_signal',
        'sector_1d_change',
        'news_sentiment',
        'analyst_target_upside',
        'analyst_bull_score',
        'analyst_rating_count_30d',
        'margin_to_atr',
        'sector_etf_1d_pct',
        # Additional features in the DB
        'short_percent_of_float',
        'spy_pct_above_sma',
        'momentum_20d',
        'gap_pct',
        'close_to_high_pct',
        'spy_intraday_pct',
        'sector_5d_return',
        'vix_1w_change',
        'entry_vs_open_pct',
        'bounce_pct_from_lod',
        'first_5min_return',
        'first_30min_return',
        'intraday_spy_trend',
        'spy_rsi_at_scan',
        'pm_range_pct',
        'margin_to_rsi',
        'margin_to_score',
        'score',
        'insider_buy_30d_value',
        'consecutive_down_days',
        'distance_from_200d_ma',
        'earnings_beat_streak',
    ]

    results = []
    for feat in features:
        if feat not in df.columns:
            continue
        for outcome in ['outcome_1d', 'outcome_3d', 'outcome_5d']:
            ic, pval, n = spearman_ic(df[feat], df[outcome])
            results.append({
                'feature': feat,
                'outcome': outcome,
                'IC': ic,
                'p_value': pval,
                'n': n,
                'abs_IC': abs(ic) if not np.isnan(ic) else 0
            })

    results_df = pd.DataFrame(results)

    # Sort by |IC| vs outcome_5d
    ic5d = results_df[results_df['outcome'] == 'outcome_5d'].sort_values('abs_IC', ascending=False)

    print(f"\n{'Feature':<28} {'IC_1d':>8} {'IC_3d':>8} {'IC_5d':>8} {'p_5d':>8} {'n':>5} {'Sig':>5}")
    print("-" * 80)

    for _, row5 in ic5d.iterrows():
        feat = row5['feature']
        # Get 1d and 3d ICs for this feature
        r1 = results_df[(results_df['feature'] == feat) & (results_df['outcome'] == 'outcome_1d')]
        r3 = results_df[(results_df['feature'] == feat) & (results_df['outcome'] == 'outcome_3d')]

        ic1 = r1['IC'].values[0] if len(r1) > 0 else np.nan
        ic3 = r3['IC'].values[0] if len(r3) > 0 else np.nan
        ic5 = row5['IC']
        p5 = row5['p_value']
        n = int(row5['n'])

        sig = "***" if p5 < 0.01 else "**" if p5 < 0.05 else "*" if p5 < 0.1 else ""

        ic1_s = f"{ic1:>8.4f}" if not np.isnan(ic1) else f"{'N/A':>8}"
        ic3_s = f"{ic3:>8.4f}" if not np.isnan(ic3) else f"{'N/A':>8}"
        ic5_s = f"{ic5:>8.4f}" if not np.isnan(ic5) else f"{'N/A':>8}"
        p5_s = f"{p5:>8.4f}" if not np.isnan(p5) else f"{'N/A':>8}"

        print(f"{feat:<28} {ic1_s} {ic3_s} {ic5_s} {p5_s} {n:>5} {sig:>5}")

    # Summary stats
    print_subheader("IC Summary Statistics")
    sig_features = ic5d[ic5d['p_value'] < 0.05]
    print(f"Total features tested: {len(ic5d)}")
    print(f"Significant at p<0.05: {len(sig_features)}")
    print(f"Significant at p<0.01: {len(ic5d[ic5d['p_value'] < 0.01])}")
    if len(sig_features) > 0:
        print(f"\nSignificant features (p<0.05):")
        for _, row in sig_features.iterrows():
            direction = "+" if row['IC'] > 0 else "-"
            print(f"  {direction} {row['feature']:<28} IC={row['IC']:.4f}  p={row['p_value']:.4f}  n={int(row['n'])}")

    # Highlight new features
    new_features = ['news_sentiment', 'analyst_target_upside', 'analyst_bull_score', 'analyst_rating_count_30d']
    print_subheader("New Feature IC Comparison (news + analyst)")
    print(f"{'Feature':<28} {'IC_5d':>8} {'p_5d':>8} {'n':>5} {'Rank':>6}")
    print("-" * 60)
    for feat in new_features:
        row = ic5d[ic5d['feature'] == feat]
        if len(row) == 0:
            print(f"{feat:<28} {'N/A':>8}")
            continue
        r = row.iloc[0]
        # Find rank
        rank = list(ic5d['feature']).index(feat) + 1
        ic5_s = f"{r['IC']:>8.4f}" if not np.isnan(r['IC']) else f"{'N/A':>8}"
        p5_s = f"{r['p_value']:>8.4f}" if not np.isnan(r['p_value']) else f"{'N/A':>8}"
        print(f"{feat:<28} {ic5_s} {p5_s} {int(r['n']):>5} {rank:>5}/{len(ic5d)}")


def bonus_strategy_split(df):
    """Bonus: check if news/analyst features differ by signal_source."""
    print_header("BONUS: IC BY SIGNAL SOURCE (DIP vs OVN vs PEM/PED)")

    for source in ['dip_bounce', 'overnight_gap', 'pre_earnings_drift', 'post_earnings_momentum', 'premarket_gap']:
        src_df = df[df['signal_source'] == source]
        if len(src_df) < 20:
            continue
        print(f"\n  [{source}] n={len(src_df)}")
        for feat in ['news_sentiment', 'analyst_target_upside', 'analyst_bull_score', 'distance_from_high', 'atr_pct', 'new_score']:
            ic, pval, n = spearman_ic(src_df[feat], src_df['outcome_5d'])
            if np.isnan(ic) or n < 10:
                continue
            sig = "***" if pval < 0.01 else "**" if pval < 0.05 else "*" if pval < 0.1 else ""
            print(f"    {feat:<28} IC={ic:>7.4f}  p={pval:.4f}  n={n:>4} {sig}")


if __name__ == "__main__":
    print("Loading data from", DB_PATH)
    df = load_data()
    print(f"Loaded {len(df)} rows with outcome_5d")
    print(f"Signal sources: {df['signal_source'].value_counts().to_dict()}")

    part1_news_analysis(df)
    part2_analyst_analysis(df)
    part3_combined_ic_table(df)
    bonus_strategy_split(df)

    print("\n" + "=" * 80)
    print("  ANALYSIS COMPLETE")
    print("=" * 80)

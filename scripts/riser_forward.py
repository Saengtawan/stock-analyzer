#!/usr/bin/env python3
"""riser_forward.py — forward tracker for the riser BAND+GAP+hold-EOD config (deployed 2026-06-16).

Pulls every riser_picks row, computes the hold-EOD outcome (EOD close / entry price - 1),
and reports running avg/pick + WR vs the locked backtest target (+0.46%/pick, WR ~53%).
Also flags whether each pick conforms to the band+gap filter (gain 2-3.5, gap<=0.5) so we can
confirm the filter is actually active on picks made AFTER the deploy date.

  python3 scripts/riser_forward.py                 # all picks
  python3 scripts/riser_forward.py --since 2026-06-17   # only post-deploy picks

EOD close from Alpaca IEX daily bar. Skips today if market still open (no EOD yet).
Read-only. Hold-EOD = matches backtest because RISER_EXIT_DYNAMIC=0.
"""
import os, sys, sqlite3, datetime as dt
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEPLOY_DATE = '2026-06-17'          # first cron day the band+gap config is live
TGT_AVG, TGT_WR = 0.40, 53.0        # band-only 2yr hold-EOD (gap-cap disabled 2026-06-16: skew)
BAND_LO, BAND_HI, GAP_CAP = 2.0, 3.5, 999  # GAP_CAP off — band-only conformance

def load_env():
    p = os.path.join(ROOT, '.env')
    if os.path.exists(p):
        for ln in open(p):
            ln = ln.strip()
            if ln and not ln.startswith('#') and '=' in ln:
                k, v = ln.split('=', 1); os.environ.setdefault(k.strip(), v.strip().strip('"\''))

def eod_close(sym, date, hdr):
    import requests
    r = requests.get(f'https://data.alpaca.markets/v2/stocks/{sym}/bars', headers=hdr,
                     params={'timeframe': '1Day', 'start': f'{date}T00:00:00Z',
                             'end': f'{date}T23:59:59Z', 'feed': 'iex', 'limit': 5}, timeout=20)
    bars = r.json().get('bars', [])
    return bars[-1]['c'] if bars else None

def main():
    load_env()
    since = None
    if '--since' in sys.argv:
        since = sys.argv[sys.argv.index('--since') + 1]
    key = os.environ.get('ALPACA_API_KEY') or os.environ.get('APCA_API_KEY_ID')
    sec = os.environ.get('ALPACA_SECRET_KEY') or os.environ.get('APCA_API_SECRET_KEY')
    hdr = {'APCA-API-KEY-ID': key, 'APCA-API-SECRET-KEY': sec}
    today_et = dt.datetime.now(ZoneInfo('America/New_York')).strftime('%Y-%m-%d')

    db = sqlite3.connect(os.path.join(ROOT, 'data/scan_journal.db'))
    q = "SELECT scan_date,symbol,price,gain,win_p,sector,gap FROM riser_picks"
    if since: q += f" WHERE scan_date>='{since}'"
    q += " ORDER BY scan_date"
    rows = db.execute(q).fetchall(); db.close()

    print(f"{'date':<11}{'sym':<6}{'gain':>6}{'gap':>6}{'wp':>5}{'entry':>9}{'eod':>9}{'pnl%':>7}  band+gap?")
    rets = []
    for date, sym, entry, gain, wp, sector, gap in rows:
        if date == today_et:
            print(f"{date:<11}{sym:<6}{gain:>6.1f}{(gap if gap is not None else float('nan')):>6.2f}{wp:>5.2f}{entry:>9.2f}{'(open)':>9}{'--':>7}  (today, no EOD yet)")
            continue
        ec = eod_close(sym, date, hdr)
        if ec is None or not entry:
            print(f"{date:<11}{sym:<6}{gain:>6.1f} (no EOD bar)"); continue
        pnl = (ec / entry - 1) * 100
        conform = (BAND_LO <= (gain or 0) <= BAND_HI) and (gap is None or gap <= GAP_CAP)
        post = date >= DEPLOY_DATE
        tag = ('✓' if conform else '✗ off-band') + (' [post]' if post else ' [pre]')
        gtxt = f"{gap:>6.2f}" if gap is not None else f"{'n/a':>6}"
        print(f"{date:<11}{sym:<6}{gain:>6.1f}{gtxt}{wp:>5.2f}{entry:>9.2f}{ec:>9.2f}{pnl:>+7.2f}  {tag}")
        rets.append((date, pnl, post))

    if rets:
        import statistics as st
        allr = [p for _, p, _ in rets]
        postr = [p for _, p, post in rets if post]
        def stat(a, lbl):
            if not a:
                print(f"  {lbl}: (none yet)"); return
            avg = sum(a) / len(a); wr = sum(1 for x in a if x > 0) / len(a) * 100
            dlt = avg - TGT_AVG
            print(f"  {lbl}: N={len(a)}  WR={wr:.0f}%  avg/pick={avg:+.3f}%  total={sum(a):+.1f}%  "
                  f"(vs backtest +{TGT_AVG} → Δ{dlt:+.3f})")
        print('\n=== FORWARD vs backtest (hold-EOD) ===')
        stat(allr, 'ALL picks   ')
        stat(postr, 'POST-deploy ')
        print(f'  target: avg/pick +{TGT_AVG}%, WR ~{TGT_WR:.0f}%. Need ~10-15 post-deploy picks before judging.')

if __name__ == '__main__':
    main()

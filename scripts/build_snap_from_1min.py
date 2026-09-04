"""สร้าง snaps จาก sip 1-min (cumulative ถึง T) แล้ว validate กับ live-saved snapshot วันนี้."""
import os,requests,pytz,gzip,json,numpy as np
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path('/home/saengtawan/work/project/cc/stock-analyzer')
for ln in (ROOT/'.env').read_text().splitlines():
    ln=ln.strip()
    if ln and not ln.startswith('#') and '=' in ln:
        k,v=ln.split('=',1); os.environ.setdefault(k.strip(),v.strip().strip('"\''))
ET=ZoneInfo('America/New_York'); hdr={'APCA-API-KEY-ID':os.getenv('ALPACA_API_KEY'),'APCA-API-SECRET-KEY':os.getenv('ALPACA_SECRET_KEY')}
def fetch1m(syms,date):
    out={}
    for i in range(0,len(syms),100):
        b=syms[i:i+100]
        p={'symbols':','.join(b),'timeframe':'1Min','start':f'{date}T13:30:00Z','end':f'{date}T20:05:00Z','limit':10000,'feed':'sip'}
        r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=hdr,params=p,timeout=30)
        if r.status_code!=200 or not r.json().get('bars'):
            p['feed']='iex'; r=requests.get('https://data.alpaca.markets/v2/stocks/bars',headers=hdr,params=p,timeout=30)
        if r.status_code==200: out.update(r.json().get('bars',{}))
    return out
def etmin(t): 
    d=datetime.fromisoformat(t.replace('Z','+00:00')).astimezone(ET); return d.hour*60+d.minute
def build_snap(bars,cutoff_min):  # cumulative ถึง cutoff (mins-of-day ET)
    b=[x for x in bars if etmin(x['t'])<=cutoff_min]
    if not b: return None
    o=b[0]['o']; tv=sum(x['v'] for x in b) or 1
    vw=sum(x['v']*x.get('vw',x['c']) for x in b)/tv
    return {'o':o,'h':max(x['h'] for x in b),'l':min(x['l'] for x in b),'c':b[-1]['c'],'v':sum(x['v'] for x in b),'vw':vw}
# validate วันนี้ 09:36 (mfo6 = cutoff 9*60+36=576)
date='2026-06-11'; live=json.load(gzip.open(ROOT/'data/scan_snapshots/2026-06-11_09-36-05.json.gz'))
syms=['AMD','ASML','ASTS','SNDK','TXN','STX','SPY','XLK','SMH','QQQ']
bars=fetch1m(syms,date)
print(f"{'sym':<6}{'gain_live':>10}{'gain_mine':>10}{'c_live':>10}{'c_mine':>10}{'diff_gain':>10}")
for s in syms:
    mine=build_snap(bars.get(s,[]),575)
    if not mine: print(f"  {s}: no sip"); continue
    lv=live['snaps'].get(s) or live['etf_snaps'].get(s)
    if not lv: print(f"  {s}: not in live snap"); continue
    ld=lv['dailyBar']; gl=(ld['c']/ld['o']-1)*100; gm=(mine['c']/mine['o']-1)*100
    print(f"  {s:<6}{gl:>+9.2f}%{gm:>+9.2f}%{ld['c']:>10.2f}{mine['c']:>10.2f}{gl-gm:>+9.3f}")

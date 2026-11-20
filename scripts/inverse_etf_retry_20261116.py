"""Real inverse ETF buys: implementation and directional-signal ablations."""
import json,hashlib
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.config import load_config
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
OUT=Path('runs/inverse_etf_retry_20261116');CFG=load_config('configs/win60_search.yaml')

def signals(data, times):
 c=pd.DataFrame(data.close,columns=data.symbols);r=np.log(c.TQQQ/c.IBIT);scale=r.diff().rolling(48).std()
 short=r.diff(8)/(scale*np.sqrt(8));long=r.diff(24)/(scale*np.sqrt(24));raw=(short+long)/2
 relative=np.where((short*long>0)&(raw.abs()>=.75),np.sign(raw),0)
 signals={}
 for policy in ('borrowed_anchor','funded_relative','absolute8','absolute24','absolute24_daily'):
  s=np.zeros_like(data.close)
  if policy in ('borrowed_anchor','funded_relative'):
   for i,v in enumerate(relative):
    if not v:continue
    if policy=='borrowed_anchor':s[i,data.symbols.index('TQQQ')]=v;s[i,data.symbols.index('IBIT')]=-v
    else:
     s[i,data.symbols.index('TQQQ' if v>0 else 'SQQQ')]=1
     s[i,data.symbols.index('BITI' if v>0 else 'IBIT')]=-1
  else:
   w=8 if policy=='absolute8' else 24
   x=np.log(c[['TQQQ','IBIT']]);z=x.diff(w)/(x.diff().rolling(48).std()*np.sqrt(w))
   directions=np.where(z.abs()>=.75,np.sign(z),0)
   if policy.endswith('daily'):
    # Completed prior session close; released only to the next observed date.
    days=times.tz_convert('America/New_York').strftime('%Y-%m-%d')
    daily=x.groupby(days).last();trend=np.sign(daily.diff(3)).shift(1)
    prior=trend.reindex(days).to_numpy();directions=np.where(directions==prior,directions,0)
   for i,(a,b) in enumerate(directions):
    if not a or not b:continue
    s[i,data.symbols.index('TQQQ' if a>0 else 'SQQQ')]=1
    s[i,data.symbols.index('IBIT' if b>0 else 'BITI')]=-1
  signals[policy]=s
 return signals

def main():
 plan=json.loads((OUT/'plan.json').read_text());source=json.loads((OUT/'source.json').read_text())
 assert hashlib.sha256((OUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(OUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);scores=signals(data,times)
 # Prefix invariance including prefixes cutting a session: no current final daily close access.
 for n in (100,801,1803):
  d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
  for k,v in signals(d,times[:n]).items():np.testing.assert_array_equal(v,scores[k][:n])
 bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')};rows=[];ledger=[]
 def evaluate(period,names):
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in bounds[period]]
  for cost,delay in ((1.,0),(2.,0),(1.,1)):
   for name in names:
    spec=StrategySpec(name,(),(),1,1,4,60,3,2);log=[]
    # Restrict borrowed comparator to its original two tradable assets, not zero-score distractors.
    if name=='borrowed_anchor':
     indices=[0,2];d=replace(data,symbols=('TQQQ','IBIT'),**{k:getattr(data,k)[:,indices] for k in ('open','high','low','close','volume')});s=scores[name][:,indices]
    else:d=data;s=scores[name]
    r=run_backtest(d,s,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=name!='borrowed_anchor',trade_log=log)
    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
    for t in log:
     assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
     ledger.append(dict(policy=name,period=period,cost=cost,delay=delay,**t))
    rows.append(dict(policy=name,period=period,cost=cost,delay=delay,**r.to_dict()))
 for p in ('2025H1','2025H2'):evaluate(p,plan['policies'])
 dev=pd.DataFrame(rows);anchor=dev[dev.policy=='borrowed_anchor'].set_index(['period','cost','delay'])
 dev['delta']=[r.total_return-anchor.loc[(r.period,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
 dev['dd_delta']=[r.max_drawdown-anchor.loc[(r.period,r.cost,r.delay),'max_drawdown'] for r in dev.itertuples()]
 dev.to_csv(OUT/'development.csv',index=False)
 rank=dev[dev.policy!='borrowed_anchor'].groupby('policy').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),min_delta=('delta','min'),max_dd_delta=('dd_delta','max')).reset_index()
 rank['eligible']=rank.min_rounds>=20;rank['pass']=rank.eligible&(rank.worst>0)&(rank.min_delta>0)&(rank.max_dd_delta<=0)
 rank=rank.sort_values(['eligible','worst','mean','policy'],ascending=[False,False,False,True]);rank.to_csv(OUT/'ranking.csv',index=False)
 selected=rank[rank.eligible].head(1).policy.tolist();(OUT/'selection.json').write_text(json.dumps(dict(selected=selected,approved=rank[rank['pass']].policy.tolist()),indent=2))
 evaluate('2026',['borrowed_anchor']+selected)
 diag=pd.DataFrame(rows);diag=diag[diag.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
 logs=pd.DataFrame(ledger);logs.to_json(OUT/'ledger.jsonl',orient='records',lines=True)
 counts=[]
 for key,g in logs.groupby(['policy','period','cost','delay']):
  if key[0]=='borrowed_anchor':continue
  for sym in data.symbols:counts.append(dict(zip(['policy','period','cost','delay'],key))|dict(symbol=sym,buy_rounds=sum(sym in x for x in g.bought_symbols)))
 pd.DataFrame(counts).to_csv(OUT/'ticker_usage.csv',index=False)
 (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE',evaluations=len(rows),development=30,diagnostic=len(diag),input_sha256=source['sha256'],hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['src/autogrid/engine.py','scripts/inverse_etf_retry_20261116.py','configs/win60_search.yaml']},periods=bounds,prefix_checks=15,independent_holdout=False,news_macro=False),indent=2))
 print(rank.to_string(index=False));print(diag[['policy','cost','delay','total_return','rounds','win_rate','max_drawdown','profit_factor']].to_string(index=False))
if __name__=='__main__':main()

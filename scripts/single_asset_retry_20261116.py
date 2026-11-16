"""Fixed-size single participation ablation with frozen-opportunity accounting."""
import json,hashlib,os
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals as old_signals,CFG
OUT=Path('runs/single_asset_retry_20261116');INPUT=Path('runs/inverse_etf_retry_20261116')

def signals(data,times):
 prior=old_signals(data,times);result={'funded_relative':prior['funded_relative']}
 c=pd.DataFrame(data.close,columns=data.symbols);x=np.log(c[['TQQQ','IBIT']])
 for family,w,daily in [('24',24,False),('8',8,False),('24_daily',24,True)]:
  z=x.diff(w)/(x.diff().rolling(48).std()*np.sqrt(w));directions=np.where(z.abs()>=.75,np.sign(z),0)
  if daily:
   dates=times.tz_convert('America/New_York').strftime('%Y-%m-%d');trend=np.sign(x.groupby(dates).last().diff(3)).shift(1)
   directions=np.where(directions==trend.reindex(dates).to_numpy(),directions,0)
  score=np.zeros_like(data.close)
  for i,(a,b) in enumerate(directions):
   if a:score[i,data.symbols.index('TQQQ' if a>0 else 'SQQQ')]=1
   if b:score[i,data.symbols.index('IBIT' if b>0 else 'BITI')]=-1
  result['single'+family]=score
  result['both'+family]=np.where((np.count_nonzero(score,axis=1)==2)[:,None],score,0)
  np.testing.assert_array_equal(result['both'+family],prior['absolute'+family])
 return result

def main():
 plan=json.loads((OUT/'plan.json').read_text());source=json.loads((INPUT/'source.json').read_text())
 assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);scores=signals(data,times)
 for n in (100,801,1803):
  d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
  for k,v in signals(d,times[:n]).items():np.testing.assert_array_equal(v,scores[k][:n])
 bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')}
 rows=[];ledger=[];audit=[]
 archived=pd.concat([pd.read_csv(INPUT/'development.csv'),pd.read_csv(INPUT/'diagnostic.csv')])
 aliases={'funded_relative':'funded_relative','both24':'absolute24','both8':'absolute8','both24_daily':'absolute24_daily'}
 def evaluate(period,names):
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in bounds[period]]
  for cost,delay in ((1.,0),(2.,0),(1.,1)):
   for name in names:
    log=[];spec=StrategySpec(name,(),(),1,1,4,60,3,2)
    r=run_backtest(data,scores[name],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name.startswith('single'),trade_log=log)
    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
    assert r.trades==sum(len(t['bought_symbols']) for t in log)
    if name in aliases:
     match=archived[(archived.policy==aliases[name])&(archived.period==period)&(archived.cost==cost)&(archived.delay==delay)]
     if len(match):
      for metric in ('total_return','rounds','win_rate','max_drawdown'):assert np.isclose(getattr(r,metric),match.iloc[0][metric]),(name,period,metric)
    for t in log:
     assert len(t['bought_symbols']) in (1,2)
     assert all(w<=.15 for w in t['bought_weights'])
     assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
     t.update(policy=name,period=period,cost=cost,delay=delay,positions=len(t['bought_symbols']))
     ledger.append(t)
    rows.append(dict(policy=name,period=period,cost=cost,delay=delay,**r.to_dict()))
    if name.startswith('single'):
     # Frozen replay rounds; sums/means are NOT a replayed portfolio return.
     for count in (1,2):
      g=[t for t in log if t['positions']==count]
      audit.append(dict(policy=name,period=period,cost=cost,delay=delay,positions=count,rounds=len(g),wins=sum(t['net_return']>0 for t in g),sum_round_return=sum(t['net_return'] for t in g),realized_capital_return=sum(t['pnl'] for t in g)/CFG.capital))
 for p in ('2025H1','2025H2'):evaluate(p,list(scores))
 dev=pd.DataFrame(rows);context=dev[dev.policy=='funded_relative'].set_index(['period','cost','delay'])
 dev['delta_context']=[r.total_return-context.loc[(r.period,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
 candidates=dev[dev.policy.isin(plan['candidates'])].copy();controls=dev.set_index(['policy','period','cost','delay'])
 candidates['delta_matched']=[r.total_return-controls.loc[(plan['matched_controls'][r.policy],r.period,r.cost,r.delay),'total_return'] for r in candidates.itertuples()]
 candidates['dd_delta']=[r.max_drawdown-controls.loc[(plan['matched_controls'][r.policy],r.period,r.cost,r.delay),'max_drawdown'] for r in candidates.itertuples()]
 dev.to_csv(OUT/'development.csv',index=False);candidates.to_csv(OUT/'paired_development.csv',index=False)
 rank=candidates.groupby('policy').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),min_delta=('delta_matched','min'),max_dd_delta=('dd_delta','max')).reset_index()
 rank['eligible']=rank.min_rounds>=20;rank['pass']=rank.eligible&(rank.worst>0)&(rank.min_delta>0)&(rank.max_dd_delta<=0)
 rank=rank.sort_values(['eligible','worst','mean','policy'],ascending=[False,False,False,True]);rank.to_csv(OUT/'ranking.csv',index=False)
 selected=rank[rank.eligible].head(1).policy.tolist();(OUT/'selection.json').write_text(json.dumps(dict(selected=selected,approved=rank[rank['pass']].policy.tolist()),indent=2))
 names=['funded_relative']+selected+[plan['matched_controls'][x] for x in selected]
 evaluate('2026',names)
 diag=pd.DataFrame(rows);diag=diag[diag.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
 pd.DataFrame(audit).to_csv(OUT/'frozen_attribution.csv',index=False)
 logs=pd.DataFrame(ledger);logs.to_json(OUT/'ledger.jsonl',orient='records',lines=True)
 usage=[]
 for key,g in logs.groupby(['policy','period','cost','delay']):
  for symbol in data.symbols:usage.append(dict(zip(['policy','period','cost','delay'],key))|dict(symbol=symbol,buy_rounds=sum(symbol in x for x in g.bought_symbols)))
 pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
 manifest=dict(status='COMPLETE',parent=plan['parent'],evaluations=len(rows),development=42,diagnostic=len(diag),source_path=str(INPUT/'market.csv.gz'),source_sha256=source['sha256'],source=source,periods=bounds,prefix_checks=21,prior_control_regression='All existing development controls and archived funded2026 metrics equal',independent_holdout=False,news_macro=False,raw_publication='not attempted; earlier raw upload was rejected; exact file remains local',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['src/autogrid/engine.py','scripts/single_asset_retry_20261116.py','configs/win60_search.yaml']})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(rank.to_string(index=False));print(diag[['policy','cost','delay','total_return','rounds','trades','win_rate','max_drawdown','profit_factor']].to_string(index=False))

if __name__=='__main__':
 lock=OUT/'RUNNING.lock'
 try:fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 except FileExistsError:raise SystemExit('Existing lock: inspect state, do not overwrite')
 os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

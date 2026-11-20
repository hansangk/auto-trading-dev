"""Direction-only inversion of actual four-ETF buys, guided by development labels."""
import json,hashlib,os
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from single_asset_retry_20261116 import signals as baseline_signals,CFG
from signal_decay_labels_20261116 import label_paths
OUT=Path('runs/signal_decay_retry_20261116');INPUT=Path('runs/inverse_etf_retry_20261116')

def signals(data,times):
 old=baseline_signals(data,times);anchor=old['single8'];swapped=np.zeros_like(anchor)
 for a,b in [('TQQQ','SQQQ'),('IBIT','BITI')]:
  ai,bi=map(data.symbols.index,(a,b));swapped[:,ai]=anchor[:,bi];swapped[:,bi]=anchor[:,ai]
 count=np.count_nonzero(anchor,axis=1)
 out=dict(single8=anchor,funded_relative=old['funded_relative'],flip_all8=swapped,flip_both8=np.where((count==2)[:,None],swapped,anchor),flip_single8=np.where((count==1)[:,None],swapped,anchor))
 for name,s in out.items():
  if name in ('single8','funded_relative'):continue
  np.testing.assert_array_equal(np.count_nonzero(s,axis=1),count)
  np.testing.assert_array_equal(np.sum(s>0,axis=1),np.sum(anchor>0,axis=1))
  np.testing.assert_array_equal(np.sum(s<0,axis=1),np.sum(anchor<0,axis=1))
 return out

def main():
 plan=json.loads((OUT/'plan.json').read_text());source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);scores=signals(data,times)
 for n in (100,801,1803):
  d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
  for k,v in signals(d,times[:n]).items():np.testing.assert_array_equal(v,scores[k][:n])
 # Same opportunity/entry/exit labels, raw actual ETF paths; not account replay.
 paired=[]
 for name in ('single8','flip_all8'):
  labels=label_paths(data,times,scores[name])
  for key,g in labels.groupby(['period','positions','delay','hold']):
   paired.append(dict(policy=name,**dict(zip(['period','positions','delay','hold'],key)),labels=len(g),mean_gross_bps=g.gross_mean.mean()*1e4,mean_net_base_bps=(g.gross_mean.mean()-.00046)*1e4))
 pd.DataFrame(paired).to_csv(OUT/'paired_forward_labels.csv',index=False)
 bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')};rows=[];ledger=[];attribution=[]
 prior=Path('runs/single_asset_retry_20261116');archived=pd.concat([pd.read_csv(prior/'development.csv'),pd.read_csv(prior/'diagnostic.csv')]);archived['period']=archived['period'].astype(str)
 def evaluate(period,names):
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in bounds[period]]
  for cost,delay in ((1.,0),(2.,0),(1.,1)):
   for name in names:
    log=[];spec=StrategySpec(name,(),(),1,1,4,60,3,2)
    r=run_backtest(data,scores[name],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='funded_relative',trade_log=log)
    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
    assert r.trades==sum(len(t['bought_symbols']) for t in log)
    if name in plan['controls']:
     p=archived[(archived.policy==name)&(archived.period==period)&(archived.cost==cost)&(archived.delay==delay)].iloc[0]
     for k in ('total_return','rounds','win_rate','max_drawdown'):assert np.isclose(getattr(r,k),p[k])
    for t in log:
     assert all(x<=.15 for x in t['bought_weights'])
     assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
     t.update(policy=name,period=period,cost=cost,delay=delay,positions=len(t['bought_symbols']));ledger.append(t)
    rows.append(dict(policy=name,period=period,cost=cost,delay=delay,**r.to_dict()))
    for count in (1,2):
     g=[t for t in log if t['positions']==count]
     attribution.append(dict(policy=name,period=period,cost=cost,delay=delay,positions=count,rounds=len(g),realized_net=sum(t['pnl'] for t in g)/CFG.capital,**{k:sum((t['equity']-t['pnl'])*t[k]/CFG.capital for t in g) for k in ('long_gross_return','short_gross_return','cost_return')}))
 for p in ('2025H1','2025H2'):evaluate(p,plan['controls']+plan['candidates'])
 dev=pd.DataFrame(rows);anchor=dev[dev.policy=='single8'].set_index(['period','cost','delay'])
 dev['delta']=[r.total_return-anchor.loc[(r.period,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
 dev['dd_delta']=[r.max_drawdown-anchor.loc[(r.period,r.cost,r.delay),'max_drawdown'] for r in dev.itertuples()]
 dev.to_csv(OUT/'development.csv',index=False)
 rank=dev[dev.policy.isin(plan['candidates'])].groupby('policy').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),min_delta=('delta','min'),max_dd_delta=('dd_delta','max')).reset_index()
 rank['eligible']=rank.min_rounds>=20;rank['pass']=rank.eligible&(rank.worst>0)&(rank.min_delta>0)&(rank.max_dd_delta<=0)
 rank=rank.sort_values(['eligible','worst','mean','policy'],ascending=[False,False,False,True]);rank.to_csv(OUT/'ranking.csv',index=False)
 chosen=rank[rank.eligible].head(1).policy.tolist();(OUT/'selection.json').write_text(json.dumps(dict(selected=chosen,approved=rank[rank['pass']].policy.tolist()),indent=2))
 evaluate('2026',plan['controls']+chosen)
 diag=pd.DataFrame(rows);diag=diag[diag.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
 pd.DataFrame(attribution).to_csv(OUT/'attribution.csv',index=False);pd.DataFrame(ledger).to_json(OUT/'ledger.jsonl',orient='records',lines=True)
 usage=[]
 for key,g in pd.DataFrame(ledger).groupby(['policy','period','cost','delay']):
  for sym in data.symbols:usage.append(dict(zip(['policy','period','cost','delay'],key))|dict(symbol=sym,buy_rounds=sum(sym in x for x in g.bought_symbols)))
 pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
 manifest=dict(status='COMPLETE',parent=plan['parent'],evaluations=len(rows),development=30,diagnostic=len(diag),input_sha256=source['sha256'],source=source,periods=bounds,independent_holdout=False,news_macro=False,prefix_checks=15,control_regression='all cells identical to previous single8/funded_relative',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['src/autogrid/engine.py','scripts/signal_decay_labels_20261116.py','scripts/direction_exhaustion_retry_20261116.py','configs/win60_search.yaml']})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(rank.to_string(index=False));print(diag[['policy','cost','delay','total_return','rounds','win_rate','max_drawdown','profit_factor']].to_string(index=False))
if __name__=='__main__':
 lock=OUT/'RUNNING.lock'
 fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

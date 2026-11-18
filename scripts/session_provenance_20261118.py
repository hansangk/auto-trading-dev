"""Fixed-policy session audit with matched ledger attribution and full replay."""
from pathlib import Path
from dataclasses import asdict
import hashlib,json,os
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals as anchor_signals,CFG
from event_path_signals import candidates,signals
from session_signal_provenance import mask_session_signals
OUT=Path('runs/session_provenance_20261118')
INPUT=Path('runs/inverse_etf_retry_20261116/market.csv.gz')
STRESS=[('base',1,0),('cost2',2,0),('delay1',1,1)]

def main():
 if (OUT/'manifest.json').exists():raise SystemExit('Complete output protected')
 digest=hashlib.sha256(INPUT.read_bytes()).hexdigest()
 assert digest=='e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd'
 data=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
 days=times.tz_convert('America/New_York').date
 grid=candidates();names=[c['name'] for c in grid];lags={c['name']:c['p2'] for c in grid};lags['anchor']=0
 scores={c['name']:signals(data,times,c) for c in grid};scores['anchor']=anchor_signals(data,times)['funded_relative']
 masked={(n,p,d):scores[n] if p=='legacy' else mask_session_signals(scores[n],times,d,lags[n],p)
         for n in names+['anchor'] for p in ('legacy','score','event') for d in (0,1)}
 rows=[];attribution=[];ticker=[];calls=0
 def evaluate(n,policy,start,end,scenario,cost,delay,state=None):
  nonlocal calls
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (start,end)]
  log=[];spec=StrategySpec(n,(),(),1,1,4,60,3,2)
  r=run_backtest(data,masked[n,policy,delay],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,
                 trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=n!='anchor',account_state=state)
  calls+=1
  assert np.isclose(np.prod([1+x['net_return'] for x in log])-1,r.total_return)
  for t in log:
   assert all(0<w<=.15000001 for w in t['bought_weights'])
   k=t['signal_index'];entry=pd.Timestamp(t['entry']).tz_convert('America/New_York').date()
   if policy=='event':assert days[k-lags[n]]==days[k]==entry
   if policy=='legacy':
    attribution.append(dict(name=n,start=start,end=end,scenario=scenario,
                 original_event_same_session=bool(days[k-lags[n]]==entry),
                 score_same_session=bool(days[k]==entry),gross=t['gross_return'],cost=t['cost_return'],net=t['net_return']))
  for symbol in data.symbols:ticker.append(dict(name=n,policy=policy,start=start,scenario=scenario,symbol=symbol,buys=sum(symbol in x['bought_symbols'] for x in log)))
  row=dict(name=n,policy=policy,start=start,end_exclusive=end,scenario=scenario,**r.to_dict())
  rows.append(row);return row
 periods=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]
 for n in names+['anchor']:
  for policy in ('legacy','score','event'):
   for a,b in periods:
    for scenario,cost,delay in STRESS:evaluate(n,policy,a,b,scenario,cost,delay)
 dev=pd.DataFrame(rows);dev.to_csv(OUT/'development.csv',index=False)
 rank=dev[(dev.policy=='event')&(dev.name!='anchor')].groupby('name').agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),halt=('mdd_halt','max')).sort_values(['worst','mean'],ascending=False)
 ref=dev[(dev.name=='anchor')&(dev.policy=='event')].set_index(['start','scenario'])
 rank['pass']=[r.min_rounds>=20 and r.worst>0 and not r.halt and all(x.total_return>ref.loc[(x.start,x.scenario),'total_return'] and x.max_drawdown<=ref.loc[(x.start,x.scenario),'max_drawdown'] for x in dev[(dev.name==n)&(dev.policy=='event')].itertuples()) for n,r in rank.iterrows()]
 rank.to_csv(OUT/'development_ranking.csv');eligible=rank[rank.min_rounds>=20];selected=eligible.index[:1].tolist()
 (OUT/'selection.json').write_text(json.dumps(dict(selected=selected,approved=rank[rank['pass']].index.tolist()),indent=2))
 for n in ['anchor']+selected:
  for policy in ('legacy','score','event'):
   for scenario,cost,delay in STRESS:evaluate(n,policy,'2026-01-01','2026-11-14',scenario,cost,delay)
 pd.DataFrame(rows)[lambda x:x.start=='2026-01-01'].to_csv(OUT/'diagnostic.csv',index=False)
 # Fixed development-selected model only, no recent parameter search.
 for months,a in [(3,'2026-08-14'),(6,'2026-05-14')]:
  for n in ['anchor']+selected:
   for policy in ('legacy','event'):
    for scenario,cost,delay in STRESS:evaluate(n,policy,a,'2026-11-14',scenario,cost,delay)
 # Causal training selection among four frozen policies. <=4 candidates stressed.
 decisions=[];walk=[];states={}
 for months in (3,6):
  for month in pd.date_range('2026-01-01','2026-11-01',freq='MS'):
   a=(month-pd.DateOffset(months=months)).strftime('%Y-%m-%d');b=month.strftime('%Y-%m-%d');end=min(month+pd.offsets.MonthBegin(1),pd.Timestamp('2026-11-14')).strftime('%Y-%m-%d')
   train=[]
   for n in names:
    cells=[evaluate(n,'event',a,b,*stress) for stress in STRESS]
    if min(c['rounds'] for c in cells)>=20 and min(c['total_return'] for c in cells)>0 and not any(c['mdd_halt'] for c in cells):train.append((min(c['total_return'] for c in cells),n))
   chosen=max(train)[1] if train else None
   decisions.append(dict(months=months,month=b,train_start=a,chosen=chosen,eligible=len(train)))
   for scenario,cost,delay in STRESS:
    state=states.setdefault((months,scenario),AccountState());before=state.equity or CFG.capital
    if chosen:r=evaluate(chosen,'event',b,end,scenario,cost,delay,state)
    else:r=dict(total_return=0.,rounds=0,win_rate=0.,max_drawdown=0.)
    walk.append(dict(months=months,month=b,scenario=scenario,chosen=chosen,equity=state.equity or before,**r))
 pd.DataFrame(decisions).to_csv(OUT/'monthly_decisions.csv',index=False);pd.DataFrame(walk).to_csv(OUT/'monthly.csv',index=False)
 frame=pd.DataFrame(attribution)
 frame.groupby(['name','start','scenario','score_same_session','original_event_same_session']).agg(rounds=('net','size'),gross_sum=('gross','sum'),cost_sum=('cost','sum'),net_sum=('net','sum')).to_csv(OUT/'frozen_ledger_attribution.csv')
 pd.DataFrame(rows).to_csv(OUT/'all_evaluations.csv',index=False);pd.DataFrame(ticker).to_csv(OUT/'ticker_usage.csv',index=False)
 files=['scripts/session_provenance_20261118.py','scripts/session_signal_provenance.py','scripts/event_path_signals.py','scripts/slot_signals.py','src/autogrid/engine.py','configs/win60_search.yaml']
 (OUT/'manifest.json').write_text(json.dumps(dict(status='COMPLETE',calls=calls,selected=selected,approved=rank[rank['pass']].index.tolist(),new_alpha_configs=0,input_sha256=digest,hashes={f:hashlib.sha256(Path(f).read_bytes()).hexdigest() for f in files},independent_validation=False,news_macro=False,orders=0),indent=2))
 print(rank.to_string());print('calls',calls,'selected',selected)

if __name__=='__main__':
 lock=OUT/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 try:main()
 finally:lock.unlink()

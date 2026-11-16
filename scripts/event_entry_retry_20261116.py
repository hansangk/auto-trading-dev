"""Completed-bar event-onset entry gate; frozen attribution versus full replay."""
import json,hashlib,os
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from direction_exhaustion_retry_20261116 import signals as old_signals,CFG
OUT=Path('runs/event_entry_retry_20261116');INPUT=Path('runs/inverse_etf_retry_20261116')

def event_mask(score):
 previous=np.vstack([np.zeros((1,score.shape[1])),score[:-1]])
 # Current nonzero allocation only: deactivation by itself is not a new entry.
 return np.any((score!=0)&(score!=previous),axis=1)

def signals(data,times):
 old=old_signals(data,times);base=old['flip_all8'];gate=event_mask(base)
 return dict(flip_all8=base,funded_relative=old['funded_relative'],event_onset8=np.where(gate[:,None],base,0))

def main():
 plan=json.loads((OUT/'plan.json').read_text());source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);scores=signals(data,times);gate=event_mask(scores['flip_all8'])
 for n in (100,801,1803):
  d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
  for k,v in signals(d,times[:n]).items():np.testing.assert_array_equal(v,scores[k][:n])
 # Audit prior DEV ledgers before new replay. Original signal_index also handles delay.
 oldroot=Path('runs/signal_decay_retry_20261116');prior_logs=pd.read_json(oldroot/'ledger.jsonl',lines=True);audit=[]
 for key,g in prior_logs[(prior_logs.policy=='flip_all8')&(prior_logs.period!='2026')].groupby(['period','cost','delay']):
  for admitted in (True,False):
   subset=[r for r in g.to_dict('records') if bool(gate[r['signal_index']])==admitted]
   audit.append(dict(zip(['period','cost','delay'],key))|dict(admitted=admitted,rounds=len(subset),sum_round_return=sum(r['net_return'] for r in subset),realized_pnl_initial=sum(r['pnl'] for r in subset)/CFG.capital,cost_initial=sum((r['equity']-r['pnl'])*r['cost_return'] for r in subset)/CFG.capital))
 pd.DataFrame(audit).to_csv(OUT/'prior_reentry_audit.csv',index=False)
 bounds={'2025H1':('2025-01-01','2025-07-01'),'2025H2':('2025-07-01','2026-01-01'),'2026':('2026-01-01','2026-11-14')};rows=[];ledger=[];frozen=[];contrib=[]
 archived=pd.concat([pd.read_csv(oldroot/'development.csv'),pd.read_csv(oldroot/'diagnostic.csv')]);archived['period']=archived.period.astype(str)
 def evaluate(period,names):
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in bounds[period]]
  for cost,delay in ((1.,0),(2.,0),(1.,1)):
   for name in names:
    log=[];spec=StrategySpec(name,(),(),1,1,4,60,3,2)
    r=run_backtest(data,scores[name],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='funded_relative',trade_log=log)
    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
    assert r.trades==sum(len(t['bought_symbols']) for t in log)
    if name!='event_onset8':
     p=archived[(archived.policy==name)&(archived.period==period)&(archived.cost==cost)&(archived.delay==delay)].iloc[0]
     for k in ('total_return','rounds','win_rate','max_drawdown'):assert np.isclose(getattr(r,k),p[k])
    for t in log:
     assert all(w<=.15 for w in t['bought_weights'])
     assert np.isclose(t['long_gross_return']+t['short_gross_return']-t['cost_return'],t['net_return'])
     if name=='event_onset8':assert gate[t['signal_index']]
     t.update(policy=name,period=period,cost=cost,delay=delay,positions=len(t['bought_symbols']));ledger.append(t)
    rows.append(dict(policy=name,period=period,cost=cost,delay=delay,**r.to_dict()))
    contrib.append(dict(policy=name,period=period,cost=cost,delay=delay,**{k:sum((t['equity']-t['pnl'])*t[k]/CFG.capital for t in log) for k in ('long_gross_return','short_gross_return','cost_return','net_return')}))
    if name=='flip_all8':
     for admitted in (True,False):
      subset=[t for t in log if bool(gate[t['signal_index']])==admitted]
      frozen.append(dict(period=period,cost=cost,delay=delay,admitted=admitted,rounds=len(subset),sum_round_return=sum(t['net_return'] for t in subset),realized_initial=sum(t['pnl'] for t in subset)/CFG.capital))
 for p in ('2025H1','2025H2'):evaluate(p,list(scores))
 dev=pd.DataFrame(rows);control=dev[dev.policy=='flip_all8'].set_index(['period','cost','delay'])
 dev['delta']=[r.total_return-control.loc[(r.period,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
 dev['dd_delta']=[r.max_drawdown-control.loc[(r.period,r.cost,r.delay),'max_drawdown'] for r in dev.itertuples()]
 dev.to_csv(OUT/'development.csv',index=False);c=dev[dev.policy=='event_onset8'];eligible=bool((c.rounds>=20).all());passed=eligible and bool((c.total_return>0).all() and(c.delta>0).all() and(c.dd_delta<=0).all())
 selection=dict(selected=['event_onset8'] if eligible else [],eligible=eligible,promotion_pass=passed,worst=float(c.total_return.min()),worst_delta=float(c.delta.min()),min_rounds=int(c.rounds.min()))
 (OUT/'selection.json').write_text(json.dumps(selection,indent=2))
 evaluate('2026',['flip_all8','funded_relative']+selection['selected'])
 allrows=pd.DataFrame(rows);diag=allrows[allrows.period=='2026'];diag.to_csv(OUT/'diagnostic.csv',index=False)
 pd.DataFrame(frozen).to_csv(OUT/'frozen_attribution.csv',index=False);pd.DataFrame(contrib).to_csv(OUT/'contributions.csv',index=False)
 logs=pd.DataFrame(ledger);logs.to_json(OUT/'ledger.jsonl',orient='records',lines=True);usage=[]
 for key,g in logs.groupby(['policy','period','cost','delay']):
  for sym in data.symbols:usage.append(dict(zip(['policy','period','cost','delay'],key))|dict(symbol=sym,buy_rounds=sum(sym in x for x in g.bought_symbols)))
 pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
 manifest=dict(status='COMPLETE',parent=plan['parent'],evaluations=len(rows),development=18,diagnostic=len(diag),input_sha256=source['sha256'],source=source,periods=bounds,independent_holdout=False,news_macro=False,prefix_checks=9,control_regression='all previous development/diagnostic controls match',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['src/autogrid/engine.py','scripts/event_entry_retry_20261116.py','configs/win60_search.yaml']})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(selection);print(diag[['policy','cost','delay','total_return','rounds','trades','win_rate','max_drawdown','profit_factor']].to_string(index=False))
if __name__=='__main__':
 lock=OUT/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

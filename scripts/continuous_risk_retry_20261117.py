"""Fixed-decision monthly risk continuity and state-component ablation."""
import json,hashlib,os
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals as anchor_signals,CFG
from creative_quant_signals_20261116 import signals
OUT=Path('runs/continuous_risk_retry_20261117');PREV=Path('runs/creative_grid_retry_20261116');INPUT=Path('runs/inverse_etf_retry_20261116')
STRESS=((1.,0),(2.,0),(1.,1))

def main():
 source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
 grid=json.loads((PREV/'candidates.json').read_text());byid={c['name']:c for c in grid};byid['anchor']=dict(name='anchor',hold=4,target=3)
 prior=pd.read_csv(PREV/'walkforward_monthly.csv');decisions=prior[(prior.policy=='adaptive')&(prior.cost==1)&(prior.delay==0)][['months','month','chosen']].copy();decisions.to_csv(OUT/'fixed_decisions.csv',index=False)
 needed=set(decisions.chosen.dropna())|{'anchor'};scores={n:(anchor_signals(data,times)['funded_relative'] if n=='anchor' else signals(data,times,byid[n])) for n in needed};zeros=np.zeros_like(data.close)
 months=sorted(decisions.month.unique());rows=[];events=[];states=[];calls=0
 for strategy,window in [('anchor',0),('adaptive',3),('adaptive',6)]:
  for mode in ('reset_all','carry_peak','carry_all'):
   for cost,delay in STRESS:
    state=AccountState(equity=CFG.capital,peak=CFG.capital,daily_start=CFG.capital);segment=[];ledger=[]
    for month in months:
     name='anchor' if strategy=='anchor' else decisions[(decisions.months==window)&(decisions.month==month)].iloc[0].chosen
     name=None if pd.isna(name) else str(name);m=pd.Timestamp(month);end=min(m+pd.offsets.MonthBegin(1),pd.Timestamp('2026-11-14')).strftime('%Y-%m-%d')
     a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in [month,end]]
     if mode=='reset_all':state=AccountState(equity=state.equity,peak=state.equity,daily_start=state.equity)
     elif mode=='carry_peak':state.loss_streak=0;state.cooldown_until=-1;state.current_date=None;state.daily_start=state.equity
     before=dict(equity=state.equity,peak=state.peak,killed=state.killed,loss_streak=state.loss_streak)
     c=byid[name] if name else dict(hold=4,target=3);score=scores[name] if name else zeros;log=[]
     spec=StrategySpec(name or 'cash',(),(),1,1,c['hold'],60,c['target'],2)
     r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='anchor',trade_log=log,account_state=state);calls+=1
     assert np.isclose(before['equity']*np.prod([1+t['net_return'] for t in log]),state.equity)
     assert not before['killed'] or not log
     if mode!='reset_all':assert state.peak>=before['peak'] and (not before['killed'] or state.killed)
     assert all(all(w<=.15 for w in t['bought_weights']) for t in log)
     if mode=='reset_all':
      p=prior[(prior.policy==strategy)&(prior.cost==cost)&(prior.delay==delay)&(prior.month==month)]
      if strategy=='adaptive':p=p[p.months==window]
      p=p.iloc[0];assert np.isclose(r.total_return,p.total_return) and r.rounds==p.rounds,(month,strategy,window)
     for t in log:
      events.append(dict(strategy=strategy,window=window,mode=mode,cost=cost,delay=delay,month=month,**t));ledger.append(t)
     segment.append(dict(strategy=strategy,window=window,mode=mode,cost=cost,delay=delay,month=month,chosen=name,total_return=r.total_return,rounds=r.rounds,**before,after_equity=state.equity,after_peak=state.peak,after_killed=state.killed,after_loss_streak=state.loss_streak))
    states.extend(segment);ret=np.array([t['net_return'] for t in ledger]);eq=np.r_[CFG.capital,[t['equity'] for t in ledger]];peak=np.maximum.accumulate(eq)
    wins=ret[ret>0];loss=ret[ret<0];pf=float(wins.sum()/abs(loss.sum())) if len(loss) else (float('inf') if len(wins) else 0)
    rows.append(dict(strategy=strategy,window=window,mode=mode,cost=cost,delay=delay,total_return=state.equity/CFG.capital-1,max_drawdown=float(abs((eq/peak-1).min())),rounds=len(ledger),trades=sum(len(t['bought_symbols']) for t in ledger),win_rate=float((ret>0).mean()) if len(ret) else 0,profit_factor=pf,costs=sum((t['equity']-t['pnl'])*t['cost_return'] for t in ledger),mdd_halt=state.killed,ever_halted=any(r['after_killed'] for r in segment),first_halt_month=next((r['month'] for r in segment if r['after_killed']),None)))
 # Uninterrupted anchor is reference for split-boundary invariance.
 reference=[]
 for cost,delay in STRESS:
  a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in ['2026-01-01','2026-11-14']];log=[]
  r=run_backtest(data,scores['anchor'],StrategySpec('anchor',(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,trade_log=log);calls+=1
  got=next(x for x in rows if x['strategy']=='anchor' and x['mode']=='carry_all' and x['cost']==cost and x['delay']==delay)
  for k in ('total_return','rounds','win_rate','max_drawdown','profit_factor'):assert np.isclose(got[k],getattr(r,k)),(k,got[k],getattr(r,k))
  reference.append(dict(cost=cost,delay=delay,**r.to_dict()))
 pd.DataFrame(rows).to_csv(OUT/'summary.csv',index=False);pd.DataFrame(states).to_csv(OUT/'monthly_state.csv',index=False);pd.DataFrame(reference).to_csv(OUT/'uninterrupted_anchor.csv',index=False)
 logs=pd.DataFrame(events);logs.to_json(OUT/'ledger.jsonl',orient='records',lines=True)
 counts=[]
 for key,g in logs.groupby(['strategy','window','mode','cost','delay']):
  for sym in data.symbols:counts.append(dict(zip(['strategy','window','mode','cost','delay'],key))|dict(symbol=sym,buy_count=sum(sym in x for x in g.bought_symbols)))
 pd.DataFrame(counts).to_csv(OUT/'ticker_usage.csv',index=False)
 manifest=dict(status='COMPLETE',source=source,input_sha256=source['sha256'],previous_grid_size=len(grid),reused_decision_count=len(decisions),unique_account_scenarios=len(rows),engine_calls=calls,completed_period='2026-01-01/2026-11-13',independent_holdout=False,news_macro=False,hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['src/autogrid/engine.py','scripts/continuous_risk_retry_20261117.py','configs/win60_search.yaml',str(PREV/'walkforward_monthly.csv')]})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 print(pd.DataFrame(rows)[['strategy','window','mode','cost','delay','total_return','max_drawdown','rounds','mdd_halt']].to_string(index=False));print('calls',calls,flush=True)
if __name__=='__main__':
 lock=OUT/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

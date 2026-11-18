"""New gap/volume/cross-response/rejection grid with continuous-risk reselection."""
import json,hashlib,os
from pathlib import Path
from dataclasses import replace
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest,AccountState
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals as anchors,CFG
from event_path_signals import candidates,signals
OUT=Path('runs/event_path_20261118');INPUT=Path('runs/inverse_etf_retry_20261116');STRESS=((1.,0),(2.,0),(1.,1))

def main():
 plan=json.loads((OUT/'plan.json').read_text());source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);grid=candidates();byid={c['name']:c for c in grid}
 byid['anchor']=dict(name='anchor',family='anchor',hold=4,target=3,stop_bps=60)
 scores={c['name']:signals(data,times,c) for c in grid};scores['anchor']=anchors(data,times)['funded_relative']
 # Exit parameters do not change entries: cache computation for each unique feature signature.
 for n in (100,801,1803):
  d=replace(data,timestamps=data.timestamps[:n],**{k:getattr(data,k)[:n] for k in ('open','high','low','close','volume')})
  for c in grid:np.testing.assert_array_equal(signals(d,times[:n],c),scores[c['name']][:n])
 # Pair on identical event, use both actual ETF price paths and one exit.
 day=times.tz_convert('America/New_York').date
 cohort=[]
 for i in range(len(times)-2):
  if times[i].year!=2025 or day[i]!=day[i+2]:continue
  for side in ('fade','continue'):
   chosen=np.flatnonzero(scores[side+'_wait0'][i])
   if not len(chosen):continue
   for wait in (0,1):
    gross=.15*(data.close[i+2,chosen]/data.open[i+1+wait,chosen]-1).sum()
    cohort.append(dict(half=1+int(times[i].month>6),side=side,wait=wait,gross=gross,net=gross-.15*len(chosen)*.00046))
 pd.DataFrame(cohort).groupby(['half','side','wait']).agg(events=('net','size'),mean_gross=('gross','mean'),mean_net=('net','mean')).to_csv(OUT/'matched.csv')
 cache={};logs={};evaluations=0
 def evaluate(name,start,end,cost=1.,delay=0):
  nonlocal evaluations
  key=(name,start,end,cost,delay)
  if key not in cache:
   c=byid[name];a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in (start,end)];log=[]
   spec=StrategySpec(name,(),(),1,1,c['hold'],60,c['target'],2)
   result=run_backtest(data,scores[name],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='anchor',trade_log=log)
   assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
   assert result.trades==sum(len(t['bought_symbols']) for t in log)
   assert all(all(w<=.15 for w in t['bought_weights']) for t in log)
   cache[key]=dict(name=name,family=c['family'],start=start,end_exclusive=end,cost=cost,delay=delay,**result.to_dict());logs[key]=log;evaluations+=1
  return cache[key]
 devperiods=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01')]
 def shortlist(start_end,number=2):
  rows=[evaluate(c['name'],a,b) for c in grid for a,b in start_end];frame=pd.DataFrame(rows)
  rank=frame.groupby(['name','family']).agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min')).reset_index();rank=rank[rank.min_rounds>=20].sort_values(['worst','mean','name'],ascending=[False,False,True])
  return rank.head(8).name.tolist(),frame,rank
 ids,base,rank=shortlist(devperiods);base.to_csv(OUT/'development_screen.csv',index=False);rank.to_csv(OUT/'screen_ranking.csv',index=False)
 (OUT/'shortlist.json').write_text(json.dumps(ids,indent=2));dev=[]
 for name in ['anchor']+ids:
  for a,b in devperiods:
   for cost,delay in STRESS:dev.append(evaluate(name,a,b,cost,delay))
 dev=pd.DataFrame(dev);control=dev[dev.name=='anchor'].set_index(['start','cost','delay'])
 dev['delta_anchor']=[r.total_return-control.loc[(r.start,r.cost,r.delay),'total_return'] for r in dev.itertuples()]
 dev['dd_delta']=[r.max_drawdown-control.loc[(r.start,r.cost,r.delay),'max_drawdown'] for r in dev.itertuples()];dev.to_csv(OUT/'development_stress.csv',index=False)
 rank2=dev[dev.name!='anchor'].groupby(['name','family']).agg(worst=('total_return','min'),mean=('total_return','mean'),min_rounds=('rounds','min'),min_delta=('delta_anchor','min'),max_dd_delta=('dd_delta','max'),any_halt=('mdd_halt','max')).reset_index();rank2['eligible']=rank2.min_rounds>=20;rank2['pass']=rank2.eligible&(rank2.worst>0)&(rank2.min_delta>0)&(rank2.max_dd_delta<=0)&(~rank2.any_halt)
 rank2=rank2.sort_values(['eligible','worst','mean','name'],ascending=[False,False,False,True]);rank2.to_csv(OUT/'stress_ranking.csv',index=False);selected=rank2[rank2.eligible].head(3).name.tolist()
 (OUT/'selection.json').write_text(json.dumps(dict(selected=selected,approved=rank2[rank2['pass']].name.tolist()),indent=2))
 diag=[evaluate(n,'2026-01-01','2026-11-14',cost,delay) for n in ['anchor']+selected for cost,delay in STRESS];pd.DataFrame(diag).to_csv(OUT/'diagnostic.csv',index=False)
 # Controlled factorial neighbors in development; do not conflate this with stress evidence.
 ablations=[]
 for name in selected:
  c=byid[name]
  for factor in ('p1','p2','hold','target'):
   peers=[p for p in grid if p['family']==c['family'] and all(p[k]==c[k] for k in ('p1','p2','hold','target') if k!=factor) and p[factor]!=c[factor]]
   for p in peers:
    for a,b in devperiods:ablations.append(dict(selected=name,factor=factor,neighbor=p['name'],start=a,selected_return=evaluate(name,a,b)['total_return'],neighbor_return=evaluate(p['name'],a,b)['total_return']))
 pd.DataFrame(ablations).to_csv(OUT/'factor_ablations.csv',index=False)
 print('development shortlist complete; selected',selected,flush=True)
 # Full-window fit rankings describe recent suitability, not OOS selection.
 recent=[];recentwinners=[];recentcontrols=[]
 for months,start in [(3,'2026-08-14'),(6,'2026-05-14')]:
  for cost,delay in STRESS:recentcontrols.append(dict(months=months,**evaluate('anchor',start,'2026-11-14',cost,delay)))
  rows=[evaluate(c['name'],start,'2026-11-14') for c in grid];f=pd.DataFrame(rows);f['months']=months;recent.extend(f.to_dict('records'))
  eligible=f[f.rounds>=20].sort_values(['total_return','name'],ascending=[False,True]);winner=eligible.iloc[0]['name'] if len(eligible) else None
  if winner:
   for cost,delay in STRESS:recentwinners.append(dict(months=months,in_sample=True,**evaluate(winner,start,'2026-11-14',cost,delay)))
 pd.DataFrame(recentcontrols).to_csv(OUT/'recent_anchor.csv',index=False);pd.DataFrame(recent).to_csv(OUT/'recent_rankings.csv',index=False);pd.DataFrame(recentwinners).to_csv(OUT/'recent_fitted_winners.csv',index=False)
 # Causal month selection, with account state carried across all target months.
 wf=[];wftrades=[];training=[];deployments=[];account_states={}
 for months in (3,6):
  for month in pd.date_range('2026-01-01','2026-11-01',freq='MS'):
   start=(month-pd.DateOffset(months=months)).strftime('%Y-%m-%d');cut=month.strftime('%Y-%m-%d');end=min(month+pd.offsets.MonthBegin(1),pd.Timestamp('2026-11-14')).strftime('%Y-%m-%d')
   shortlist_ids,_,_=shortlist([(start,cut)]);rows=[]
   for n in shortlist_ids:
    cells=[evaluate(n,start,cut,cost,delay) for cost,delay in STRESS];worst=min(r['total_return'] for r in cells);minrounds=min(r['rounds'] for r in cells);halt=any(r['mdd_halt'] for r in cells)
    rows.append(dict(month=cut,months=months,name=n,train_start=start,train_end_exclusive=cut,worst=worst,min_rounds=minrounds,any_halt=halt,eligible=minrounds>=20 and worst>0 and not halt,mean=np.mean([r['total_return'] for r in cells])))
   training.extend(rows);ranks=pd.DataFrame(rows,columns=['month','months','name','train_start','train_end_exclusive','worst','min_rounds','any_halt','eligible','mean'])
   ranks=ranks[ranks.eligible.astype(bool)].sort_values(['worst','mean','name'],ascending=[False,False,True]);chosen=ranks.iloc[0]['name'] if len(ranks) else None
   with (OUT/'walkforward_decisions.jsonl').open('a') as f:f.write(json.dumps(dict(month=cut,months=months,chosen=chosen,train_start=start,train_end_exclusive=cut))+'\n')
   a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in [cut,end]]
   for policy in ('adaptive','anchor'):
    name=chosen if policy=='adaptive' else 'anchor';c=byid[name] if name else dict(hold=4,target=3);score=scores[name] if name else np.zeros_like(data.close)
    for cost,delay in STRESS:
     key=(months,policy,cost,delay);state=account_states.setdefault(key,AccountState(equity=CFG.capital,peak=CFG.capital,daily_start=CFG.capital));before_kill=state.killed;before_peak=state.peak;before_equity=state.equity;log=[]
     spec=StrategySpec(name or 'cash',(),(),1,1,c['hold'],60,c['target'],2)
     r=run_backtest(data,score,spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='anchor',trade_log=log,account_state=state);evaluations+=1
     assert np.isclose(before_equity*np.prod([1+t['net_return'] for t in log]),state.equity)
     assert r.trades==sum(len(t['bought_symbols']) for t in log)
     assert not before_kill or not log
     assert state.peak>=before_peak
     assert all(all(w<=.15 for w in t['bought_weights']) for t in log)
     result=dict(month=cut,months=months,policy=policy,chosen=name,name=name or 'cash',start=cut,end_exclusive=end,cost=cost,delay=delay,**r.to_dict(),equity=state.equity,peak=state.peak,killed=state.killed)
     wf.append(result);deployments.append(result)
     for t in log:wftrades.append(dict(month=cut,months=months,policy=policy,cost=cost,delay=delay,**t))
     with (OUT/'account_checkpoints.jsonl').open('a') as f:f.write(json.dumps(dict(month=cut,months=months,policy=policy,cost=cost,delay=delay,state=vars(state)),default=str)+'\n')
  print('continuous walk-forward',months,'months complete',flush=True)
 pd.DataFrame(training).to_csv(OUT/'walkforward_training.csv',index=False);w=pd.DataFrame(wf);w.to_csv(OUT/'walkforward_monthly.csv',index=False);alllogs=pd.DataFrame(wftrades);alllogs.to_json(OUT/'walkforward_ledger.jsonl',orient='records',lines=True)
 summaries=[]
 for key,g in w.groupby(['months','policy','cost','delay']):
  months,policy,cost,delay=key;ledger=alllogs[(alllogs.months==months)&(alllogs.policy==policy)&(alllogs.cost==cost)&(alllogs.delay==delay)] if len(alllogs) else pd.DataFrame()
  rets=ledger.net_return.to_numpy() if len(ledger) else np.array([]);curve=np.r_[CFG.capital,ledger.equity.to_numpy()] if len(ledger) else np.array([CFG.capital]);wins=rets[rets>0];loss=rets[rets<0]
  summaries.append(dict(zip(['months','policy','cost','delay'],key))|dict(months_tested=len(g),active_months=int((g.rounds>0).sum()),total_return=float(curve[-1]/CFG.capital-1),max_drawdown=float(abs((curve/np.maximum.accumulate(curve)-1).min())),rounds=len(rets),trades=int(ledger.bought_symbols.map(len).sum()) if len(ledger) else 0,win_rate=float((rets>0).mean()) if len(rets) else 0,profit_factor=float(wins.sum()/abs(loss.sum())) if len(loss) else (float('inf') if len(wins) else 0),mdd_halt=bool(g.iloc[-1].killed),first_halt_month=next((r.month for r in g.itertuples() if r.killed),None)))
 for item in summaries:
  if item['policy']=='anchor':
   reference=next(r for r in diag if r['name']=='anchor' and r['cost']==item['cost'] and r['delay']==item['delay'])
   for k in ('total_return','rounds','win_rate','max_drawdown','profit_factor'):assert np.isclose(item[k],reference[k]),('anchor continuity',k)
 pd.DataFrame(summaries).to_csv(OUT/'walkforward_summary.csv',index=False)
 # Frozen anchor opportunities versus candidate activity are descriptive attribution,
 # not causal returns for new signal families. Full replay is already separate.
 audit=[]
 for name in selected:
  for a,b in devperiods:
   evaluate('anchor',a,b)
   for t in logs[('anchor',a,b,1.,0)]:
    i=t['signal_index'];active=bool(np.any(scores[name][i]));same=bool(np.array_equal(scores[name][i],scores['anchor'][i]));audit.append(dict(selected=name,start=a,signal_index=i,candidate_active=active,identical_roles=same,baseline_net_return=t['net_return']))
 pd.DataFrame(audit,columns=['selected','start','signal_index','candidate_active','identical_roles','baseline_net_return']).to_csv(OUT/'frozen_opportunity_audit.csv',index=False)
 pd.concat([pd.DataFrame(cache.values()).assign(run_type='isolated_window'),pd.DataFrame(deployments).assign(run_type='continuous_month')]).to_csv(OUT/'all_evaluations.csv',index=False)
 manifest=dict(status='COMPLETE',candidate_count=len(grid),shortlist=len(ids),diagnostic_selected=selected,evaluations=evaluations,source=source,source_sha256=source['sha256'],parent=plan['parent'],independent_holdout=False,news_macro=False,walkforward_policy='Train trailing3/6months, staged shortlist, positiveallstress/min20/nohalts, freeze choice then nextmonth. AccountState carries equity/peak/streak/cooldown/kill, never monthly reset',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/event_path_20261118.py','scripts/event_path_signals.py','configs/win60_search.yaml','src/autogrid/engine.py']})
 (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));(OUT/'candidates.json').write_text(json.dumps(grid,indent=2))
 print(json.dumps(dict(evaluations=evaluations,selected=selected,approved=rank2[rank2['pass']].name.tolist()),indent=2),flush=True)
 print(pd.DataFrame(recentwinners).reindex(columns=['months','name','cost','delay','total_return','rounds']).to_string(index=False),flush=True)
 print(pd.DataFrame(summaries)[['months','policy','cost','delay','total_return','active_months']].to_string(index=False),flush=True)
if __name__=='__main__':
 if (OUT/'walkforward_decisions.jsonl').exists():raise SystemExit('Existing decisions: use new run or verified resume; do not overwrite')
 lock=OUT/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

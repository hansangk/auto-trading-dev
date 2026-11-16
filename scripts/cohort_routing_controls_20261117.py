"""Matched-exit source/union controls and routing intervention support audit."""
import json,hashlib
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from microstructure_signals_20261117 import signals as component_signals
from cohort_routing_signals_20261117 import candidates,signals
from inverse_etf_retry_20261116 import CFG
OUT=Path('runs/cohort_routing_retry_20261117');INPUT=Path('runs/inverse_etf_retry_20261116');OLD=Path('runs/microstructure_grid_retry_20261117');STRESS=((1.,0),(2.,0),(1.,1))

def source_union(gap,volume):
 """Per-role gap priority, no summation or duplicate asset allocations."""
 if gap.shape!=volume.shape or gap.ndim!=2 or gap.shape[1]!=4:raise ValueError('Expected same4column buy roles')
 result=volume.copy()
 for columns in ([0,1],[2,3]):
  active=np.any(gap[:,columns]!=0,axis=1)
  result[np.ix_(active,columns)]=gap[np.ix_(active,columns)]
 return result

def main():
 source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);grid=candidates();byid={c['name']:c for c in grid};chosen=json.loads((OUT/'selection.json').read_text())['selected']
 gap=component_signals(data,times,dict(family='gap_absorption',p1=.5,p2=.6));vol=component_signals(data,times,dict(family='volume_pressure',p1=6,p2=2));arrays={'gap':gap,'volume':vol,'union':source_union(gap,vol)}
 oldmanifest=json.loads((OLD/'manifest.json').read_text());assert oldmanifest['source_sha256']==source['sha256'];assert oldmanifest['hashes']['src/autogrid/engine.py']==hashlib.sha256(Path('src/autogrid/engine.py').read_bytes()).hexdigest()
 for f in ['scripts/microstructure_signals_20261117.py','configs/win60_search.yaml']:assert oldmanifest['hashes'][f]==hashlib.sha256(Path(f).read_bytes()).hexdigest()
 old=pd.read_csv(OLD/'all_evaluations.csv');current=pd.concat([pd.read_csv(OUT/'development_stress.csv'),pd.read_csv(OUT/'diagnostic.csv')]);controlcache={};logs={};calls=0;reused=0;rows=[];frozen=[]
 periods=[('2025-01-01','2025-07-01'),('2025-07-01','2026-01-01'),('2026-01-01','2026-11-14')]
 def evaluate(source_name,hold,target,a,b,cost,delay):
  nonlocal calls,reused
  key=(source_name,hold,target,a,b,cost,delay)
  if key not in controlcache:
   name=(f'gap_absorption_p0.5_q0.6_h{hold}_t{target}' if source_name=='gap' else f'volume_pressure_p6_q2_h{hold}_t{target}')
   previous=old[(old.name==name)&(old.start==a)&(old.end_exclusive==b)&(old.cost==cost)&(old.delay==delay)] if source_name!='union' else pd.DataFrame()
   if len(previous):r=previous.iloc[0].to_dict();reused+=1
   else:
    start,stop=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in [a,b]];log=[]
    result=run_backtest(data,arrays[source_name],StrategySpec(source_name,(),(),1,1,hold,60,target,2),CFG.execution,CFG.risk,CFG.capital,start,stop,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=True,trade_log=log)
    assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
    r=result.to_dict();logs[key]=log;calls+=1
   controlcache[key]=dict(source=source_name,hold=hold,target=target,start=a,end_exclusive=b,cost=cost,delay=delay,**{k:r[k] for k in ['total_return','rounds','trades','win_rate','max_drawdown','profit_factor','mdd_halt']})
  return controlcache[key]
 for name in chosen:
  c=byid[name];score=signals(data,times,c)
  for a,b in periods:
   for cost,delay in STRESS:
    selected=current[(current.name==name)&(current.start==a)&(current.end_exclusive==b)&(current.cost==cost)&(current.delay==delay)].iloc[0]
    for source_name in arrays:
     control=evaluate(source_name,c['hold'],c['target'],a,b,cost,delay)
     rows.append(dict(selected=name,selected_return=selected.total_return,delta_control=selected.total_return-control['total_return'],**control))
    if cost==1 and delay==0:
     for t in logs[('union',c['hold'],c['target'],a,b,cost,delay)]:
      i=t['signal_index'];frozen.append(dict(selected=name,start=a,signal_index=i,unchanged=bool(np.array_equal(score[i],arrays['union'][i])),active=bool(np.any(score[i])),baseline_net_return=t['net_return']))
 # Recent fit winner's same-exit controls; all descriptive, not new selection.
 recent=[];winners=pd.read_csv(OUT/'recent_fitted_winners.csv')
 for c0 in winners[(winners.cost==1)&(winners.delay==0)].itertuples():
  c=byid[c0.name]
  for source_name in arrays:
   for cost,delay in STRESS:recent.append(dict(months=c0.months,selected=c0.name,**evaluate(source_name,c['hold'],c['target'],c0.start,c0.end_exclusive,cost,delay)))
 pd.DataFrame(rows).to_csv(OUT/'matched_source_controls.csv',index=False);pd.DataFrame(recent).to_csv(OUT/'recent_source_controls.csv',index=False);pd.DataFrame(frozen).to_csv(OUT/'union_frozen_attribution.csv',index=False)
 interventions=[]
 for c in grid[::4]:
  s=signals(data,times,c)
  for label,a,b in [('2025H1','2025-01-01','2025-07-01'),('2025H2','2025-07-01','2026-01-01'),('2025','2025-01-01','2026-01-01')]:
   keep=(times>=pd.Timestamp(a,tz='UTC'))&(times<pd.Timestamp(b,tz='UTC'))
   interventions.append(dict(family=c['family'],p1=c['p1'],p2=c['p2'],period=label,changed_bars=int((keep&np.any(s!=arrays['union'],axis=1)).sum()),active_bars=int((keep&np.any(s!=0,axis=1)).sum()),entry_hash=hashlib.sha256(s[keep].tobytes()).hexdigest()))
 pd.DataFrame(interventions).to_csv(OUT/'routing_interventions.csv',index=False)
 manifest=json.loads((OUT/'manifest.json').read_text());manifest['main_engine_evaluations']=manifest['evaluations'];manifest['control_new_engine_calls']=calls;manifest['control_prior_cache_reused']=reused;manifest['evaluations']+=calls;manifest['hashes']['scripts/cohort_routing_controls_20261117.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2))
 (OUT/'control_manifest.json').write_text(json.dumps(dict(new_engine_calls=calls,prior_cache_reused=reused,unique_controls=len(controlcache),warning='Source union same exits per selected candidate, no weight summation; fixed intervention cohort attribution is not routed account return'),indent=2));print(dict(newcalls=calls,reused=reused));print(pd.DataFrame(interventions).query('period=="2025"').groupby('family').changed_bars.agg(['min','max']).to_string())
if __name__=='__main__':
 if (OUT/'control_manifest.json').exists():raise SystemExit('Controls already completed; use verified new run, do not double count')
 main()

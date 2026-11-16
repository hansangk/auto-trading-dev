"""Causal hash-cash negative controls, not a new alpha strategy grid."""
import hashlib,json,os
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals as anchor_signals,CFG
from microstructure_signals_20261117 import signals as component_signals
from cohort_routing_signals_20261117 import signals as route_signals
from cohort_routing_controls_20261117 import source_union
OUT=Path('runs/role_information_retry_20261117');INPUT=Path('runs/inverse_etf_retry_20261116');STRESS=((1.,0),(2.,0),(1.,1));STYLES=('event_role','event_shared','session_role','hour_role')

def uniform_hash(token,seed):
 return int.from_bytes(hashlib.sha256(f'{seed}|{token}'.encode()).digest()[:8],'big')/2**64

def calibrate_probabilities(source,routed,times):
 keep=(times>=pd.Timestamp('2025-01-01',tz='UTC'))&(times<pd.Timestamp('2025-07-01',tz='UTC'));hours=times.tz_convert('America/New_York').hour
 rates=[];table=[]
 for role,cols in enumerate(([0,1],[2,3])):
  active=np.any(source[:,cols]!=0,axis=1);same=active&np.all(source[:,cols]==routed[:,cols],axis=1);n=int((keep&active).sum());p=float((keep&same).sum()/n) if n else 0.;rates.append(p)
  for hour in range(9,16):
   mask=keep&active&(hours==hour);count=int(mask.sum());q=float((mask&same).sum()/count) if count>=20 else p
   table.append(dict(role=role,hour=hour,count=count,retained=int((mask&same).sum()),p=q,flat_p=p,fallback=count<20))
 return rates,table

def cash_scores(source,times,style,seed,rates,table):
 if style not in STYLES:raise ValueError('Unknown cash control style')
 out=np.zeros_like(source);local=times.tz_convert('America/New_York');byhour={(r['role'],r['hour']):r['p'] for r in table}
 for i,t in enumerate(times):
  for role,cols in enumerate(([0,1],[2,3])):
   if not np.any(source[i,cols]):continue
   token=(f'{local[i].date()}|{role}' if style=='session_role' else f'{t.isoformat()}|'+('shared' if style=='event_shared' else str(role)))
   p=byhour.get((role,int(local[i].hour)),rates[role]) if style=='hour_role' else rates[role]
   if uniform_hash(token,seed)<p:out[i,cols]=source[i,cols]
 return out

def main():
 source=json.loads((INPUT/'source.json').read_text());assert hashlib.sha256((INPUT/'market.csv.gz').read_bytes()).hexdigest()==source['sha256']
 data=load_market_data(INPUT/'market.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True)
 g=component_signals(data,times,dict(family='gap_absorption',p1=.5,p2=.6));v=component_signals(data,times,dict(family='volume_pressure',p1=6,p2=2));union=source_union(g,v)
 router=route_signals(data,times,dict(family='daily_regime',p1=.4,p2=.15,hold=4,target=3));rates,table=calibrate_probabilities(union,router,times);pd.DataFrame(table).to_csv(OUT/'cash_calibration.csv',index=False)
 scores={'union':union,'router':router,'anchor':anchor_signals(data,times)['funded_relative']};controls=[]
 for style in STYLES:
  for seed in range(16):
   name=f'{style}_s{seed:02d}';controls.append(dict(name=name,style=style,seed=seed));scores[name]=cash_scores(union,times,style,seed,rates,table)
 # Fixed seeds for stress. They are not chosen based on control profits.
 selected=[c['name'] for c in controls if c['seed']<2];(OUT/'control_selection.json').write_text(json.dumps(dict(stress_controls=selected,rule='Predeclared seeds0/1perstyle;never choose most profitable random controls',alpha_candidates=0),indent=2))
 rows=[];logs={};calls=0;cache={}
 def evaluate(name,start,end,cost=1.,delay=0):
  nonlocal calls
  key=(name,start,end,cost,delay)
  if key not in cache:
   a,b=[int(times.searchsorted(pd.Timestamp(t,tz='UTC'))) for t in [start,end]];log=[]
   r=run_backtest(data,scores[name],StrategySpec(name,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='anchor',trade_log=log);calls+=1
   assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,r.total_return)
   assert r.trades==sum(len(t['bought_symbols']) for t in log)
   cache[key]=dict(name=name,start=start,end_exclusive=end,cost=cost,delay=delay,**r.to_dict());logs[key]=log
  return cache[key]
 for period,a,b in [('2025H1','2025-01-01','2025-07-01'),('2025H2','2025-07-01','2026-01-01')]:
  for c in controls:rows.append(dict(period=period,phase='base_all_controls',**evaluate(c['name'],a,b)))
  for n in ['union','router','anchor']+selected:
   for cost,delay in STRESS:rows.append(dict(period=period,phase='stress',**evaluate(n,a,b,cost,delay)))
 pd.DataFrame(rows).to_csv(OUT/'control_development.csv',index=False)
 # No new alpha candidate or performance-selected shortlist. Fixed controls only.
 diagnostic=[]
 for n in ['union','router','anchor']+selected:
  for cost,delay in STRESS:diagnostic.append(evaluate(n,'2026-01-01','2026-11-14',cost,delay))
 pd.DataFrame(diagnostic).to_csv(OUT/'control_diagnostic.csv',index=False)
 recent=[]
 for months,a in [(3,'2026-08-14'),(6,'2026-05-14')]:
  for n in ['union','router','anchor']+selected:
   for cost,delay in STRESS:recent.append(dict(months=months,**evaluate(n,a,'2026-11-14',cost,delay)))
 pd.DataFrame(recent).to_csv(OUT/'recent_fixed_controls.csv',index=False)
 # Matching in full replay is expected participation, not guaranteed realized turnover.
 match=[];contributions=[]
 for key,row in cache.items():
  name,a,b,cost,delay=key;log=logs[key];match.append(dict(name=name,start=a,end_exclusive=b,cost=cost,delay=delay,actual_rounds=row['rounds'],actual_orders=row['trades'],turnover=row['turnover']))
  contributions.append(dict(name=name,start=a,end_exclusive=b,cost=cost,delay=delay,**{k:sum((t['equity']-t['pnl'])*t[k]/CFG.capital for t in log) for k in ('long_gross_return','short_gross_return','cost_return','net_return')}))
 pd.DataFrame(match).to_csv(OUT/'realized_turnover.csv',index=False);pd.DataFrame(contributions).to_csv(OUT/'replay_contributions.csv',index=False);pd.DataFrame(cache.values()).to_csv(OUT/'all_control_evaluations.csv',index=False)
 # Aggregate null controls without selecting a profitable seed.
 f=pd.DataFrame(rows);summary=[]
 for key,cells in f[(f.phase=='stress')&f.name.isin(selected)].groupby(['period','cost','delay']):
  a=cells.iloc[0].start;b=cells.iloc[0].end_exclusive;target=evaluate('router',a,b,key[1],key[2]);summary.append(dict(zip(['period','cost','delay'],key))|dict(controls=len(cells),control_mean=cells.total_return.mean(),control_median=cells.total_return.median(),control_min=cells.total_return.min(),control_max=cells.total_return.max(),router_return=target['total_return'],router_minus_control_mean=target['total_return']-cells.total_return.mean(),control_mean_orders=cells.trades.mean(),router_orders=target['trades']))
 pd.DataFrame(summary).to_csv(OUT/'control_comparison.csv',index=False)
 manifest=dict(status='COMPLETE',control_replicates=64,stress_replicates=8,alpha_candidates=0,engine_calls=calls,calibration='2025H1signalcounts only;H1fitted/H2causal fixed calibration;not liveperformance',source=source,source_sha256=source['sha256'],independent_holdout=False,news_macro=False,warning='Fullreplay controls match expected retention via H1probabilities, not exact realized turnover; actualturnover explicitly saved. Exact matching only in separate frozenrole permutations.',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/role_cash_controls_20261117.py','src/autogrid/engine.py','configs/win60_search.yaml']})
 (OUT/'cash_manifest.json').write_text(json.dumps(manifest,indent=2));print('calls',calls);print(pd.DataFrame(summary).to_string(index=False));print(pd.DataFrame(diagnostic).query('name in ["union","router","anchor"]')[['name','cost','delay','total_return','rounds','win_rate','max_drawdown']].to_string(index=False))
if __name__=='__main__':
 if (OUT/'cash_manifest.json').exists():raise SystemExit('Alreadycomplete; use newverifiedrun, no overwrite')
 lock=OUT/'RUNNING.lock';fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.write(fd,str(os.getpid()).encode());os.close(fd)
 try:main()
 finally:lock.unlink()

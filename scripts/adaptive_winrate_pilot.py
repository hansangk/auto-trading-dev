"""Retrospective rolling strategy-selection experiment, not a live system."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.random_validation import _parse_specs
from autogrid.strategy import build_score

data=load_market_data('data/alpaca_iex/market_final_45m.csv')
cfg=load_config('configs/win60_search.yaml')
specs=_parse_specs('runs/win60_45m/top30.csv')[:5]
cache=FeatureCache(data)
plans={i:(s,build_score(s,cache)) for i,s in enumerate(specs)}
dates=np.asarray(pd.to_datetime(data.timestamps,utc=True).date)
days, starts=np.unique(dates,return_index=True)
regimes=np.full(len(dates),-1,dtype=int)
choices=[]
active=None
# Rebalance every 10 trading days, using only the previous 60 days.
for day in range(60,len(days),10):
    start=int(starts[day-60]); end=int(starts[day]); stop=int(starts[min(day+10,len(days)-1)]) if day+10<len(days) else len(dates)
    evaluation=[]
    for idx,(spec,score) in plans.items():
        res=run_backtest(data,score,spec,cfg.execution,cfg.risk,cfg.capital,start,end)
        evaluation.append((idx,res))
    current=next((r for i,r in evaluation if i==active),None)
    if current is None or current.win_rate < .5 or current.total_return <= 0:
        viable=[(i,r) for i,r in evaluation if r.rounds>=20 and r.win_rate>=.5 and r.total_return>0 and r.profit_factor>1]
        active=max(viable,key=lambda p:(p[1].total_return,p[1].win_rate))[0] if viable else None
    regimes[end:stop]=-1 if active is None else active
    choices.append({'evaluation_date':str(days[day]),'training_start':str(days[day-60]),'training_end':str(days[day-1]),'chosen_strategy':None if active is None else specs[active].strategy_id})

rows=[]
for year in (2024,2025,2026):
    a=int(np.searchsorted(days,pd.Timestamp(f'{year}-01-01').date())); b=int(np.searchsorted(days,pd.Timestamp(f'{year+1}-01-01').date()))
    if year==2024: a=max(a,60)
    start=int(starts[a]); stop=int(starts[b]) if b<len(days) else len(dates)
    for mode in ('adaptive','fixed_candidate'):
        spec,score=plans[0]
        for mult in (1.,2.):
            z=run_backtest(data,score,spec,cfg.execution,cfg.risk,cfg.capital,start,stop,cost_multiplier=mult,regime_plan=(regimes,plans) if mode=='adaptive' else None)
            rows.append({'year':year,'mode':mode,'cost':mult,**z.to_dict()})
out=Path('runs/adaptive_winrate_pilot');out.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(out/'results.csv',index=False)
pd.DataFrame(choices).to_csv(out/'choices.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'strategies':[s.strategy_id for s in specs],'training_days':60,'review_days':10,'selection':'switch if prior 60-day hypothetical win rate below 50% or return <=0; choose prior-period best positive candidate meeting minimum 20 rounds, else cash','warning':'exploratory selected strategies; previously inspected data; prior win rates are candidate simulations, not actual portfolio trailing results; not independent OOS'},indent=2))
print(pd.DataFrame(rows)[['year','mode','cost','total_return','win_rate','rounds','max_drawdown']].to_string(index=False))

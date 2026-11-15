"""Exploratory walk-forward grid, 2026 is previously inspected, not holdout."""
from pathlib import Path
import itertools, json
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.random_validation import _parse_specs
from autogrid.strategy import build_score

data=load_market_data('data/alpaca_iex/market_final_45m.csv'); cfg=load_config('configs/win60_search.yaml')
specs=_parse_specs('runs/win60_45m/top30.csv')[:5]; cache=FeatureCache(data)
plans={i:(s,build_score(s,cache)) for i,s in enumerate(specs)}
dates=np.asarray(pd.to_datetime(data.timestamps,utc=True).date); days,starts=np.unique(dates,return_index=True)
out=Path('runs/adaptive_grid_experiment'); out.mkdir(parents=True,exist_ok=True)
rows=[]; diary=[]
for lookback,review,threshold in itertools.product((40,60,100),(10,20),(.5,.6)):
    regime=np.full(len(dates),-1,dtype=int); active=None
    for d in range(lookback,len(days),review):
        lo=int(starts[d-lookback]); hi=int(starts[d]); stop=int(starts[d+review]) if d+review<len(days) else len(dates)
        results=[]
        for i,(s,score) in plans.items():
            z=run_backtest(data,score,s,cfg.execution,cfg.risk,cfg.capital,lo,hi)
            results.append((i,z))
        now=next((z for i,z in results if i==active),None)
        if now is None or now.win_rate<threshold or now.total_return<=0:
            viable=[(i,z) for i,z in results if z.rounds>=20 and z.win_rate>=threshold and z.total_return>0 and z.profit_factor>1]
            active=max(viable,key=lambda p:(p[1].total_return,p[1].win_rate))[0] if viable else None
        regime[hi:stop]=-1 if active is None else active
        diary.append({'lookback':lookback,'review':review,'threshold':threshold,'date':str(days[d]),'active':active})
    for label,start,end in [('development','2024-08-01','2026-01-01'),('recent','2026-01-01','2026-11-14')]:
        a=int(np.searchsorted(days,pd.Timestamp(start).date())); b=int(np.searchsorted(days,pd.Timestamp(end).date()))
        lo=int(starts[a]); hi=int(starts[b]) if b<len(days) else len(dates)
        for cost in (1.,2.):
            spec,score=plans[0]; z=run_backtest(data,score,spec,cfg.execution,cfg.risk,cfg.capital,lo,hi,cost_multiplier=cost,regime_plan=(regime,plans))
            rows.append({'lookback':lookback,'review':review,'threshold':threshold,'period':label,'cost':cost,**z.to_dict()})
pd.DataFrame(rows).to_csv(out/'results.csv',index=False);pd.DataFrame(diary).to_csv(out/'choices.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'strategies':[s.strategy_id for s in specs],'caveat':'strategy pool was selected using future periods, and 2026 repeatedly inspected; results exploratory, not unbiased OOS'},indent=2))
print(pd.DataFrame(rows).query('cost==1')[['lookback','review','threshold','period','total_return','win_rate','rounds','max_drawdown']].to_string(index=False))

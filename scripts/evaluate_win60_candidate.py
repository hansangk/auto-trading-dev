import json
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import build_score
from autogrid.random_validation import _parse_specs

cfg=load_config('configs/win60_search.yaml')
spec=next(s for s in _parse_specs('runs/win60_45m/top30.csv') if s.strategy_id=='c8eeb78d1a44')
rows=[]
def evaluate(path, tag, quarterly=False):
    data=load_market_data(path); score=build_score(spec,FeatureCache(data))
    ts=pd.to_datetime(data.timestamps,utc=True); dates=pd.Series(ts).dt.tz_localize(None).dt.to_period('Q')
    windows=[('all',0,len(ts))]
    if quarterly:
        for q in dates.unique():
            idx=np.flatnonzero(dates==q); windows.append((str(q),int(idx[0]),int(idx[-1]+1)))
    for label,a,b in windows:
        for cost,delay in [(1,0),(2,0),(1,1),(1,2)]:
            z=run_backtest(data,score,spec,cfg.execution,cfg.risk,cfg.capital,a,b,cost,delay)
            rows.append({'dataset':tag,'period':label,'cost_multiplier':cost,'delay_bars':delay,'start':str(ts[a]),'end':str(ts[b-1]),**z.to_dict()})
for year in (2022,2023): evaluate(f'data/alpaca_iex_bito/resampled_{year}/market_45m.csv',str(year)+'_BITO',True)
evaluate('data/alpaca_iex/market_final_45m.csv','2024_2026_IBIT',True)
out=Path('runs/win60_candidate_repeat');out.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(out/'results.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'strategy_id':spec.strategy_id,'note':'retrospective; candidate chosen after examining 2026; different 2022/23 universe; quarterly tests reset equity and risk state'},indent=2))
print(pd.DataFrame(rows).query('cost_multiplier==1 and delay_bars==0')[['dataset','period','total_return','win_rate','rounds','max_drawdown']].to_string(index=False))

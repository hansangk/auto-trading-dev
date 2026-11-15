"""Prior-selected folds; stress short exclusions. Research only, no live orders."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import generate_specs, build_score

data=load_market_data('data/alpaca_iex/market_final_45m.csv')
cfg=load_config('configs/win60_search.yaml')
specs=generate_specs(cfg.grid,120,20261123,include_news=False)
by_id={s.strategy_id:s for s in specs}; cache=FeatureCache(data)
scores={s.strategy_id:build_score(s,cache) for s in specs}
dates=np.asarray(pd.to_datetime(data.timestamps,utc=True).date); days, starts=np.unique(dates,return_index=True)
selections=json.loads(Path('runs/chronological_combinations/selections.json').read_text())
rows=[]
for selection in selections:
    if not selection['chosen_ids']: continue
    spec=by_id[selection['chosen_ids'][0]]; startday=pd.Timestamp(selection['test_start']).date(); endday=pd.Timestamp(selection['test_end']).date()
    a=int(starts[np.searchsorted(days,startday)]); next_day=int(np.searchsorted(days,endday,side='right')); b=int(starts[next_day]) if next_day<len(days) else len(dates)
    for name,exclusions in [('baseline',frozenset()),('no_inverse_short',frozenset({'BITI'})),('no_leveraged_inverse_short',frozenset({'BITI','BITX'}))]:
        for cost,delay in ((1.,0),(2.,0),(1.,1)):
            r=run_backtest(data,scores[spec.strategy_id],spec,cfg.execution,cfg.risk,cfg.capital,a,b,cost,delay,short_exclude_symbols=exclusions)
            rows.append({'test_start':str(startday),'test_end':str(endday),'strategy_id':spec.strategy_id,'rule':name,'cost':cost,'delay':delay,**r.to_dict()})
out=Path('runs/retry_short_restrictions');out.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(out/'folds.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'purpose':'post-hoc isolate short restrictions, selected strategies unchanged','warning':'no new data; cost and short pnl estimated; per-fold reset; not prospective OOS','rules':{'baseline':[],'no_inverse_short':['BITI'],'no_leveraged_inverse_short':['BITI','BITX']}},indent=2))
print('rows',len(rows))

"""Exploratory chronological comparison: stricter prior-cost selection and regime gate."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import build_score, generate_specs

data=load_market_data('data/alpaca_iex/market_final_45m.csv');cfg=load_config('configs/win60_search.yaml')
specs=generate_specs(cfg.grid,120,20261123,include_news=False)
cache=FeatureCache(data);scores={s.strategy_id:build_score(s,cache) for s in specs}
dates=np.asarray(pd.to_datetime(data.timestamps,utc=True).date);days,starts=np.unique(dates,return_index=True)
spy=data.close[:,data.symbols.index('SPY')]; close=np.array([spy[(starts[k+1]-1) if k+1<len(days) else -1] for k in range(len(days))])
rows=[]; decisions=[]
for d in range(140,len(days)-19,20):
    a=int(starts[d-140]); mid=int(starts[d-40]); b=int(starts[d]); end=int(starts[d+20])
    pastret=close[d-1]/close[d-21]-1
    options=[]
    for s in specs:
        score=scores[s.strategy_id]
        train=run_backtest(data,score,s,cfg.execution,cfg.risk,cfg.capital,a,mid,2.)
        valid=run_backtest(data,score,s,cfg.execution,cfg.risk,cfg.capital,mid,b,2.)
        if train.rounds>=40 and valid.rounds>=15 and train.total_return>0 and valid.total_return>0 and train.long_pnl>0 and train.short_pnl>0 and valid.long_pnl>0 and valid.short_pnl>0:
            options.append((min(train.total_return,valid.total_return),s))
    options.sort(key=lambda p:(-p[0],p[1].strategy_id)); chosen=options[0][1] if options else None
    decisions.append({'test_start':str(days[d]),'test_end':str(days[d+19]),'past_spy_return':pastret,'eligible':len(options),'chosen_id':chosen.strategy_id if chosen else None})
    for rule in ('robust','robust_down'):
        permitted=chosen is not None and (rule=='robust' or pastret<0)
        for cost in (1.,2.):
            if permitted:
                z=run_backtest(data,scores[chosen.strategy_id],chosen,cfg.execution,cfg.risk,cfg.capital,b,end,cost)
                row=z.to_dict()
            else: row={'total_return':0.,'rounds':0,'win_rate':0.,'max_drawdown':0.,'long_pnl':0.,'short_pnl':0.}
            rows.append({'test_start':str(days[d]),'test_end':str(days[d+19]),'rule':rule,'cost':cost,'traded':permitted,'strategy_id':chosen.strategy_id if permitted else None,**row})
out=Path('runs/robust_regime_research');out.mkdir(parents=True,exist_ok=True)
pd.DataFrame(rows).to_csv(out/'fold_results.csv',index=False)
(out/'decisions.json').write_text(json.dumps(decisions,indent=2))
(out/'manifest.json').write_text(json.dumps({'candidate_seed':20261123,'candidate_count':len(specs),'train_days':100,'validation_days':40,'test_days':20,'selection_cost_multiplier':2,'gate':'SPY 20-day prior return negative','warning':'post-hoc regime hypothesis, reused data, equity reset per fold, not independent final validation'},indent=2))
print('folds',len(decisions),'base selected',sum(d['eligible']>0 for d in decisions))

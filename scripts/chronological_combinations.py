"""Chronological research: fixed seeded universe, select only using preceding data."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import build_score, generate_specs

data=load_market_data('data/alpaca_iex/market_final_45m.csv')
cfg=load_config('configs/win60_search.yaml')
specs=generate_specs(cfg.grid,120,20261123,include_news=False)
cache=FeatureCache(data); scores={s.strategy_id:build_score(s,cache) for s in specs}
dates=np.asarray(pd.to_datetime(data.timestamps,utc=True).date); days,starts=np.unique(dates,return_index=True)
output=Path('runs/chronological_combinations'); output.mkdir(parents=True,exist_ok=True)
rows=[]; selections=[]
for endday in range(140,len(days)-19,20):
    lo=int(starts[endday-140]); split=int(starts[endday-40]); hi=int(starts[endday]); end=int(starts[endday+20])
    candidates=[]
    for s in specs:
        score=scores[s.strategy_id]
        a=run_backtest(data,score,s,cfg.execution,cfg.risk,cfg.capital,lo,split)
        b=run_backtest(data,score,s,cfg.execution,cfg.risk,cfg.capital,split,hi)
        if a.rounds>=40 and b.rounds>=15 and a.total_return>0 and b.total_return>0 and a.profit_factor>1 and b.profit_factor>1 and a.long_pnl>0 and a.short_pnl>0 and b.long_pnl>0 and b.short_pnl>0:
            candidates.append((min(a.total_return,b.total_return),s))
    candidates.sort(key=lambda x:(-x[0],x[1].strategy_id))
    chosen=[s for _,s in candidates[:5]]
    selections.append({'train_start':str(days[endday-140]),'validation_start':str(days[endday-40]),'test_start':str(days[endday]),'test_end':str(days[endday+19]),'eligible_count':len(candidates),'chosen_ids':[s.strategy_id for s in chosen]})
    if not chosen:
        rows.append({'test_start':str(days[endday]),'test_end':str(days[endday+19]),'status':'cash','strategy_id':None,'cost':1,'delay':0,'total_return':0,'rounds':0,'win_rate':0,'max_drawdown':0});continue
    # Select the top candidate using only prior data, and separately report 5 candidates.
    for rank,s in enumerate(chosen,1):
        for cost,delay in ((1,0),(2,0),(1,1)):
            z=run_backtest(data,scores[s.strategy_id],s,cfg.execution,cfg.risk,cfg.capital,hi,end,cost,delay)
            rows.append({'test_start':str(days[endday]),'test_end':str(days[endday+19]),'status':'traded','strategy_id':s.strategy_id,'selection_rank':rank,'cost':cost,'delay':delay,**z.to_dict()})
pd.DataFrame(rows).to_csv(output/'fold_results.csv',index=False)
(output/'selections.json').write_text(json.dumps(selections,indent=2))
(output/'manifest.json').write_text(json.dumps({'seed':20261123,'candidate_count':len(specs),'train_days':100,'validation_days':40,'test_days':20,'test_equity_reset':True,'data_warning':'IEX partial; candidate grid and periods previously studied; retrospective; not fresh independent holdout'},indent=2))
print('folds',len(selections),'cash',sum(x['eligible_count']==0 for x in selections))

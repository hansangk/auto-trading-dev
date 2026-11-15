"""Retrospective fold-start regime analysis and predeclared gating ablation."""
from pathlib import Path
import json
import numpy as np
import pandas as pd

folds=pd.read_csv('runs/chronological_combinations/fold_results.csv')
base=folds[(folds.selection_rank==1)&(folds.cost==1)&(folds.delay==0)].copy()
raw=pd.read_csv('data/alpaca_iex/market_final_45m.csv')
raw['timestamp']=pd.to_datetime(raw.timestamp,utc=True)
spy=raw[raw.symbol=='SPY'].copy()
spy['date']=spy.timestamp.dt.date
daily=spy.groupby('date',sort=True).close.last()
records=[]
for _,r in base.iterrows():
    day=pd.Timestamp(r.test_start).date()
    prior=daily.loc[daily.index<day]
    assert len(prior)>=21
    past_return=prior.iloc[-1]/prior.iloc[-21]-1
    past_vol=prior.pct_change().iloc[-20:].std(ddof=1)*np.sqrt(252)
    records.append({**r.to_dict(),'prior_20d_return':past_return,'prior_20d_vol':past_vol,'trend':'up' if past_return>0 else 'down', 'volatility':'high' if past_vol>=.20 else 'low'})
x=pd.DataFrame(records)
out=Path('runs/regime_failure_analysis');out.mkdir(parents=True,exist_ok=True)
x.to_csv(out/'folds.csv',index=False)
summary=[]
for name,mask in [('all',x.index==x.index),('up',x.trend=='up'),('down',x.trend=='down'),('high_vol',x.volatility=='high'),('low_vol',x.volatility=='low'),('gate_up_lowvol',(x.trend=='up')&(x.volatility=='low'))]:
    y=x.loc[mask]; z=float(y.rounds.sum());
    summary.append({'rule':name,'folds':len(y),'rounds':int(z),'win_rate':float((y.win_rate*y.rounds).sum()/z) if z else None,'fold_return_chain':float((1+y.total_return).prod()-1),'positive_folds':int((y.total_return>0).sum()),'long_contribution':float(y.long_pnl.sum()),'short_contribution':float(y.short_pnl.sum())})
pd.DataFrame(summary).to_csv(out/'summary.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'lookback':'20 completed trading days','trend':'SPY 20-day return positive','high_vol':'20-day daily close return stdev annualized >= 20%','warning':'exploratory post-hoc filters, overlapping research, tested only on previously selected folds, not independent; folds reset risk'},indent=2))
print(pd.DataFrame(summary).to_string(index=False))

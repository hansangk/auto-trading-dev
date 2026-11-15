"""15m signals plus latest *completed* 60m features; exploratory research only."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from autogrid.config import load_config
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.features import FeatureCache
from autogrid.strategy import StrategySpec

root=Path('data/alpaca_iex'); out=Path('runs/multiframe_pilot');out.mkdir(parents=True,exist_ok=True)
for m in (15,60):
    pieces=[pd.read_csv(root/f'mtf_{y}/market_{m}m.csv') for y in (2024,2025,2026)]
    pd.concat(pieces,ignore_index=True).to_csv(out/f'market_{m}m.csv',index=False)
fast=load_market_data(out/'market_15m.csv');slow=load_market_data(out/'market_60m.csv')
assert fast.symbols==slow.symbols
cfg=load_config('configs/win60_search.yaml'); fc=FeatureCache(fast);sc=FeatureCache(slow)
fstart=pd.to_datetime(fast.timestamps,utc=True); sstart=pd.to_datetime(slow.timestamps,utc=True)
# Each bar's label is its start. Enforce its full nominal duration, even on early/partial bars.
fclose=fstart+pd.Timedelta(minutes=15); sclose=sstart+pd.Timedelta(minutes=60)
mapping=np.searchsorted(sclose.asi8,fclose.asi8,side='right')-1
valid=mapping>=0
assert np.all(sclose.asi8[mapping[valid]]<=fclose.asi8[valid])
rows=[]
for f in ('roc_10','zclose_10','rsi_7'):
 for s in ('ema_3_15','roc_10','zclose_10'):
  for weight in (.5,.75):
   slowrank=np.zeros(fast.shape,dtype=np.float32);slowrank[valid]=sc.cross_sectional_rank(s)[mapping[valid]]
   score=weight*fc.cross_sectional_rank(f)+(1-weight)*slowrank;score[~valid]=0
   for stop in (80.,150.):
    for tp in (.5,1.5):
     for hold in (3,6):
      sid=f'{f}+{s}-w{weight}-sl{stop:g}-tp{tp}-h{hold}'
      spec=StrategySpec(sid,(f,s),(weight,1-weight),1,1,hold,stop,tp,3)
      a=int(np.searchsorted(fstart.asi8,pd.Timestamp('2024-01-01',tz='UTC').value)); b=int(np.searchsorted(fstart.asi8,pd.Timestamp('2026-01-01',tz='UTC').value))
      fit=run_backtest(fast,score,spec,cfg.execution,cfg.risk,cfg.capital,a,b)
      rows.append({'strategy_id':sid,'fast_feature':f,'slow_feature':s,'weight_fast':weight,'stop_bps':stop,'take_profit_multiple':tp,'hold':hold,'fit_return':fit.total_return,'fit_win':fit.win_rate,'fit_rounds':fit.rounds,'fit_long':fit.long_pnl,'fit_short':fit.short_pnl})
frame=pd.DataFrame(rows).sort_values(['fit_return','fit_win'],ascending=False)
frame.to_csv(out/'all_development.csv',index=False)
selected=frame.head(30);results=[]
for _,r in selected.iterrows():
  fast_name=r.fast_feature; slow_name=r.slow_feature;weight=r.weight_fast
  slowrank=np.zeros(fast.shape,dtype=np.float32);slowrank[valid]=sc.cross_sectional_rank(slow_name)[mapping[valid]]
  score=weight*fc.cross_sectional_rank(fast_name)+(1-weight)*slowrank;score[~valid]=0
  spec=StrategySpec(r.strategy_id,(fast_name,slow_name),(weight,1-weight),1,1,int(r.hold),float(r.stop_bps),float(r.take_profit_multiple),3)
  b=int(np.searchsorted(fstart.asi8,pd.Timestamp('2026-01-01',tz='UTC').value))
  for cost,delay in ((1.,0),(2.,0),(1.,1)):
   z=run_backtest(fast,score,spec,cfg.execution,cfg.risk,cfg.capital,b,len(fstart),cost,delay)
   results.append({'strategy_id':r.strategy_id,'development_return':r.fit_return,'development_win':r.fit_win,'cost':cost,'delay':delay,**z.to_dict()})
pd.DataFrame(results).to_csv(out/'recent_results.csv',index=False)
(out/'manifest.json').write_text(json.dumps({'candidates':len(frame),'selected':len(selected),'fast_minutes':15,'slow_minutes':60,'alignment':'slow bar full nominal close <= fast bar nominal close; signal next available fast bar','training':'2024-2025','test':'2026 through 2026-11-13','warning':'previously examined period; IEX sparse; not independent holdout; independent resampling common timestamps may discard bars'},indent=2))
print('candidates',len(frame),'selected',len(selected),'fast bars',len(fstart),'slow bars',len(sstart))

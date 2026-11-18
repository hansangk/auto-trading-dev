"""Frozen recovery replay; no selection or fresh-sample claim."""
from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import signals,CFG
from microstructure_signals_20261117 import signals as micro
OUT=Path('runs/recovery_retry_20261118')
INPUT=Path('/workspace/scratch/290b763eac4f/auto-trading-dev/runs/inverse_etf_retry_20261116/market.csv.gz')
def main():
 if (OUT/'results.csv').exists():raise SystemExit('Already complete; preserve outputs')
 h=hashlib.sha256(INPUT.read_bytes()).hexdigest();assert h=='e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd'
 d=load_market_data(INPUT,['TQQQ','SQQQ','IBIT','BITI']);t=pd.to_datetime(d.timestamps,utc=True)
 frozen=json.loads(Path('runs/snapshot_shadow_retry_20261117/frozen_models.json').read_text())
 scores={'anchor':signals(d,t)['funded_relative'],'gap_reference':micro(d,t,frozen['gap_reference']),'cash':np.zeros_like(d.close)}
 a,b=[int(t.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in ('2026-01-01','2026-11-14')];rows=[];usage=[]
 for name,c in frozen.items():
  for scenario,cost,delay in [('base',1,0),('cost2',2,0),('delay1',1,1)]:
   log=[];spec=StrategySpec(name,(),(),1,1,c['hold'],c['stop_bps'],c['target'],2)
   r=run_backtest(d,scores[name],spec,CFG.execution,CFG.risk,CFG.capital,a,b,cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=name!='anchor')
   assert np.isclose(np.prod([1+x['net_return'] for x in log])-1,r.total_return)
   assert all(0<w<=.150000001 for x in log for w in x['bought_weights'])
   rows.append(dict(model=name,scenario=scenario,period_start='2026-01-01',period_end='2026-11-13',**r.to_dict()))
   for s in d.symbols:usage.append(dict(model=name,scenario=scenario,symbol=s,buy_rounds=sum(s in x['bought_symbols'] for x in log)))
 pd.DataFrame(rows).to_csv(OUT/'results.csv',index=False);pd.DataFrame(usage).to_csv(OUT/'ticker_usage.csv',index=False)
 paths=['src/autogrid/engine.py','scripts/recovery_retry_20261118.py','scripts/inverse_etf_retry_20261116.py','scripts/microstructure_signals_20261117.py','configs/win60_search.yaml','runs/snapshot_shadow_retry_20261117/frozen_models.json']
 (OUT/'manifest.json').write_text(json.dumps(dict(status='RECOVERY_REPLAY_COMPLETE_FRESH_DATA_BLOCKED',engine_calls=9,new_candidates=0,independent_validation=False,news_macro=False,real_orders=False,input_sha256=h,input_path=str(INPUT),parent='f29c81567ed4ce033df7d8ddeb9f9e2146472fd7',hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}),indent=2))
 print(pd.DataFrame(rows)[['model','scenario','total_return','rounds','win_rate','max_drawdown']].to_string(index=False))
if __name__=='__main__':main()

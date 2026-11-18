"""Six original actual-inverseETF regression cells; no parameter fitting."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG,signals
OUT=Path('runs/hourly_clock_retry_20261119_0300')
def main():
    target=OUT/'legacy_regression.json'
    if target.exists():raise SystemExit('Completed regression protected')
    source=Path('runs/inverse_etf_retry_20261116');p=source/'market.csv.gz'
    assert hashlib.sha256(p.read_bytes()).hexdigest()=='e0dea9e76a9c7f57b5d3791912e85473a29f5d31d4743783cf17b29a95c09fbd'
    data=load_market_data(p,['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);score=signals(data,times)['funded_relative'];prior=pd.read_csv(source/'development.csv');rows=[]
    for label,a,b in [('2025H1','2025-01-01','2025-07-01'),('2025H2','2025-07-01','2026-01-01')]:
        lo,hi=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (a,b)]
        for cost,delay in [(1,0),(2,0),(1,1)]:
            r=run_backtest(data,score,StrategySpec('funded_relative',(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,lo,hi,cost,delay,exit_mode='joint_close',funded_pair=True)
            old=prior[(prior.policy=='funded_relative')&(prior.period==label)&(prior.cost==cost)&(prior.delay==delay)].iloc[0]
            keys=['total_return','max_drawdown','rounds','win_rate','costs','trades'];passed=all(np.isclose(getattr(r,k),old[k]) for k in keys);assert passed
            rows.append(dict(period=label,cost=cost,delay=delay,passed=passed,fields=keys,**r.to_dict()))
    target.write_text(json.dumps(dict(engine_calls=6,cells=rows,policy='Original frozen funded_relative, originalunfilteredinput and legacycrosssessionsemantics. Nochange to newintraday experiment.'),indent=2));print('6 original actual-ETF regression cells PASS')
if __name__=='__main__':main()

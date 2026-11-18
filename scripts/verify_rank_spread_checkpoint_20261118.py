"""Verify saved comparator results without overwriting completed research outputs."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from rank_spread_signals import candidates,signals
from session_signal_provenance import mask_session_signals
OUT=Path('runs/rank_spread_20261118')

def main():
    target=OUT/'verification.json'
    if target.exists():raise SystemExit('Verification already preserved')
    manifest=json.loads((OUT/'manifest.json').read_text())
    for path,digest in manifest['hashes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,path
    source=Path('runs/inverse_etf_retry_20261116/market.csv.gz')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['source_sha256']
    data=load_market_data(source,['TQQQ','SQQQ','IBIT','BITI'])
    times=pd.to_datetime(data.timestamps,utc=True)
    configs={c['name']:c for c in candidates()}
    expected=pd.concat([pd.read_csv(OUT/'development_stress.csv'),pd.read_csv(OUT/'diagnostic.csv')])
    expected=expected[(expected.name=='spread_50')|((expected.name=='leader_0')&(expected.start=='2026-01-01'))]
    # leader diagnostic was not selected. Include a separately identified comparator.
    checks=[];usage=[]
    for row in expected.itertuples():
        config=configs[row.name]
        score=mask_session_signals(signals(data,times,config),times,int(row.delay),0,'event')
        a,b=[int(times.searchsorted(pd.Timestamp(x,tz='UTC'))) for x in (row.start,row.end_exclusive)]
        log=[]
        result=run_backtest(data,score,StrategySpec(row.name,(),(),1,1,4,60,3,2),CFG.execution,CFG.risk,CFG.capital,a,b,row.cost,int(row.delay),exit_mode='joint_close',funded_pair=True,funded_allow_single=True,trade_log=log)
        for metric in ('total_return','max_drawdown','rounds','win_rate','costs','trades'):
            assert np.isclose(getattr(result,metric),getattr(row,metric)),(row.name,metric)
        assert result.trades==sum(len(t['bought_symbols']) for t in log)
        for symbol in data.symbols:usage.append(dict(name=row.name,start=row.start,cost=row.cost,delay=row.delay,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
        checks.append(dict(name=row.name,start=row.start,cost=row.cost,delay=row.delay,matched=True))
    pd.DataFrame(usage).to_csv(OUT/'verified_ticker_usage.csv',index=False)
    target.write_text(json.dumps(dict(status='PASS',fresh_engine_calls=len(checks),checks=checks,input_sha256=manifest['source_sha256'],script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),note='Prior657 executions resumed. These9 verification replays are additional; no new candidates.'),indent=2))
    print('Verified',len(checks),'engine calls')
if __name__=='__main__':main()

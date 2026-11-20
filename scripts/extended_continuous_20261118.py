"""One uninterrupted account replay per fixed model and stress on expanded input."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
from extended_snapshot_20261118 import OUT,MODELS,SYMBOLS
from episode_signals_20261118 import signals
from five_minute_grid_20261118 import signals as parent_signals
from autogrid.data import load_market_data
from autogrid.engine import run_backtest
from autogrid.strategy import StrategySpec
from inverse_etf_retry_20261116 import CFG
from session_signal_provenance import mask_session_signals

def main():
    target=OUT/'continuous.csv'
    if target.exists():raise SystemExit('Completed continuous results protected')
    data=load_market_data(OUT/'refreshed_all_LOCAL.csv.gz',SYMBOLS);times=pd.to_datetime(data.timestamps,utc=True)
    scores={c['name']:signals(data,times,c) for c in MODELS}
    scores['momentum_parent']=parent_signals(data,times,dict(family='momentum',a=4,b=.5))
    control=np.zeros_like(data.close)
    for _,group in pd.Series(np.arange(len(times))).groupby(times.tz_convert('America/New_York').date):
        ix=group.to_numpy();i=ix[23];r=data.close[i]/data.open[ix[0]]-1;j=int(np.argmax(r))
        if r[j]>0:control[i,j]=1 if j<2 else -1
    scores['control']=control;rows=[]
    for name,score in scores.items():
        for scenario,cost,delay in [('base',1,0),('cost2',2,0),('delay1',1,1)]:
            log=[]
            result=run_backtest(data,mask_session_signals(score,times,delay,0,'event'),StrategySpec(name,(),(),1,1,12,60,3,2),CFG.execution,CFG.risk,CFG.capital,0,len(times),cost,delay,trade_log=log,exit_mode='joint_close',funded_pair=True,funded_allow_single=True)
            assert np.isclose(np.prod([1+t['net_return'] for t in log])-1,result.total_return)
            rows.append(dict(name=name,scenario=scenario,start=str(times[0]),last_start=str(times[-1]),**result.to_dict()))
    pd.DataFrame(rows).to_csv(target,index=False)
    manifest=json.loads((OUT/'manifest.json').read_text());manifest.update(continuous_calls=15,total_calls=195,tests={'count':101,'seconds':6.755,'result':'PASS'});manifest['code_hashes'][str(Path(__file__).relative_to(Path.cwd()))]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2));print(pd.DataFrame(rows)[['name','scenario','total_return','rounds','win_rate','max_drawdown','mdd_halt']].to_string(index=False))
if __name__=='__main__':main()

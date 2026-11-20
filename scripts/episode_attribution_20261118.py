"""First/repeated completed15-minute role events; raw labels, not account returns."""
from pathlib import Path
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from five_minute_grid_20261118 import signals
OUT=Path('runs/episode_grid_20261118')
def main():
    data=load_market_data('runs/five_minute_grid_20261118/complete_sessions_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI'])
    times=pd.to_datetime(data.timestamps,utc=True);ny=times.tz_convert('America/New_York');days=ny.date
    score=signals(data,times,dict(family='momentum',a=4,b=.5))
    rows=[];state=[None,None];last_day=None
    for k,stamp in enumerate(ny):
        if days[k]!=last_day:state=[None,None];last_day=days[k]
        if (stamp.hour*60+stamp.minute-570)%15!=10:continue
        for role,columns in enumerate(((0,1),(2,3))):
            selected=[j for j in columns if score[k,j]!=0]
            chosen=selected[0] if selected else None
            first=chosen is not None and state[role]!=chosen
            state[role]=chosen
            if chosen is None or stamp>=pd.Timestamp('2026-11-14',tz='America/New_York'):continue
            if k+12>=len(days) or days[k]!=days[k+12]:continue
            gross=.15*(data.close[k+12,chosen]/data.open[k+1,chosen]-1);cost=.15*.00046
            rows.append(dict(period='A' if stamp<pd.Timestamp('2026-11-01',tz='America/New_York') else 'B',kind='first' if first else 'repeat',day=str(days[k]),symbol=data.symbols[chosen],gross=gross,cost=cost,net=gross-cost))
    frame=pd.DataFrame(rows)
    frame.groupby(['period','kind']).agg(role_events=('net','size'),active_days=('day','nunique'),mean_gross=('gross','mean'),mean_cost=('cost','mean'),mean_net=('net','mean')).to_csv(OUT/'first_repeat_paths.csv')
    frame.to_csv(OUT/'first_repeat_LOCAL.csv',index=False)
    print(pd.read_csv(OUT/'first_repeat_paths.csv').to_string(index=False))
if __name__=='__main__':main()

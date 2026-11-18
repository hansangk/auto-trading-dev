"""Development-only raw original-event paths, grouped by box age or drift."""
from pathlib import Path
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from episode_signals_20261118 import _momentum_direction,_episode_start,signals
OUT=Path('runs/structural_grid_20261118')

def main():
    data=load_market_data('runs/extended_snapshot_20261118/refreshed_all_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI'])
    times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    events=[];actual={}
    for name,c in [('compression',dict(family='compression',a=.75,b=4)),('chase1',dict(family='chasecancel',a=1,b=.25)),('chase3',dict(family='chasecancel',a=3,b=.5))]:actual[name]=signals(data,times,c)
    traces={name:np.zeros_like(data.close) for name in actual}
    for day,group in pd.Series(np.arange(len(times))).groupby(days):
        ix=group.to_numpy();bars=[];states=[dict(ready=True,box=None,start=None,chases=[dict(direction=0,neutral=0,pending=None) for _ in (1,3)]) for _ in (0,2)]
        for pos,k in enumerate(ix):
            decision=pos%3==2
            for state,up in zip(states,(0,2)):
                if decision:
                    compact=False
                    if len(bars)>=6:
                        ref=np.median([x[0][up]-x[1][up] for x in bars[-6:-2]])
                        compact=ref>0 and np.mean([x[0][up]-x[1][up] for x in bars[-2:]])<=.75*ref
                    if not compact:state['ready']=True
                    if state['box'] is None and compact and state['ready']:
                        state['box']=(max(x[0][up] for x in bars[-2:]),min(x[1][up] for x in bars[-2:]));state['start']=pos;state['ready']=False
                    if state['box'] is not None:
                        top,bottom=state['box'];direction=int(data.close[k,up]>top)-int(data.close[k,up]<bottom)
                        if direction:
                            selected=up if direction>0 else up+1
                            if pos<77:events.append(('compression',k,selected,(pos-state['start'])//3))
                            state['box']=None
                    direction=_momentum_direction(bars,data.close[k,up],up)
                    for state2 in state['chases']:
                        if _episode_start(direction,state2):
                            selected=up if direction>0 else up+1;state2['pending']=dict(symbol=selected,start=pos,anchor=data.close[k,selected],width=bars[-1][0][selected]-bars[-1][1][selected])
                for delay,state2 in zip((1,3),state['chases']):
                    p=state2['pending']
                    if p is not None and pos>p['start'] and pos-p['start']>=delay:
                        j=p['symbol'];upper=.25 if delay==1 else .5
                        if pos-p['start']==delay and p['width']>0 and pos<77 and data.close[k,j]<=p['anchor']+upper*p['width']:events.append((f'chase{delay}',k,j,(data.close[k,j]-p['anchor'])/p['width']))
                        state2['pending']=None
            if decision:
                triple=ix[pos-2:pos+1];bars.append((data.high[triple].max(axis=0),data.low[triple].min(axis=0),data.close[k]))
    rows=[]
    for model,k,j,value in events:
        traces[model][k,j]=1 if j<2 else -1
        if times[k]>=pd.Timestamp('2026-10-19',tz='UTC') or k+12>=len(times) or days[k]!=days[k+12]:continue
        bucket=('age0' if value==0 else 'age1to2' if value<3 else 'age3plus') if model=='compression' else ('below-.75' if value<-.75 else '-.75to-.25' if value<-.25 else 'atleast-.25')
        gross=.15*(data.close[k+12,j]/data.open[k+1,j]-1)
        rows.append(dict(model=model,period='A' if times[k]<pd.Timestamp('2026-09-20',tz='UTC') else 'B',bucket=bucket,gross=gross,cost=.000069,net=gross-.000069))
    for name in actual:np.testing.assert_array_equal(traces[name],actual[name])
    pd.DataFrame(rows).groupby(['model','period','bucket']).agg(role_events=('net','size'),mean_gross=('gross','mean'),mean_cost=('cost','mean'),mean_net=('net','mean')).to_csv(OUT/'original_event_strata.csv')
    print('Original role signal arrays match source metadata reconstruction')
if __name__=='__main__':main()

"""Session-local hourly tactics. Bull/bear forecasts select actual ETFs."""
import numpy as np
import pandas as pd
from event_path_signals import signals as rejection

def candidates():
    settings={'fade':[0,.5,1.0],'opening':[1,2],'pullback':[4,8],'relative':[2,3]}
    return [dict(name=f'{family}_{p}',family=family,p1=p,p2=0,hold=4,target=3)
            for family,values in settings.items() for p in values]

def signals(data,times,c):
    days=times.tz_convert('America/New_York').date
    p=c['p1'];family=c['family']
    result=np.zeros_like(data.close)
    if family=='fade':
        result=rejection(data,times,dict(p1='fade',p2=1))
        if p:
            for bull,bear in [(0,1),(2,3)]:
                h=pd.Series(data.high[:,bull]).groupby(days).shift()
                l=pd.Series(data.low[:,bull]).groupby(days).shift()
                k=data.close[:,bull]
                result[~(k>l+p*(h-l)),bull]=0
                result[~(k<h-p*(h-l)),bear]=0
        return result
    for _,idx in pd.Series(np.arange(len(days))).groupby(days):
        ix=idx.to_numpy()
        if family=='relative':
            if len(ix)>=p:
                j=ix[p-1];r=data.close[j]/data.open[ix[0]]-1
                w=int(np.argmax(r))
                if r[w]>0:result[j,w]=1 if w<2 else -1
            continue
        for bull,bear,role in [(0,1,1),(2,3,-1)]:
            k=pd.Series(data.close[ix,bull]);h=data.high[ix,bull];l=data.low[ix,bull]
            if family=='opening':
                top=h[:p].max();bottom=l[:p].min()
                up=(k>top)&(k.shift()<=top);down=(k<bottom)&(k.shift()>=bottom)
                up.iloc[:p]=False;down.iloc[:p]=False
            else:
                # Prior EMA is warmed across sessions, touched using the completed bar.
                # Use only a bounded historical prefix for deterministic warmup.
                lo=max(0,ix[0]-8*p)
                ema=pd.Series(data.close[lo:ix[-1]+1,bull]).ewm(span=p,adjust=False,min_periods=p).mean()
                prev=ema.shift().iloc[ix-lo].to_numpy();slope=ema.diff().shift().iloc[ix-lo].to_numpy()
                up=(slope>0)&(l<=prev)&(k>prev);down=(slope<0)&(h>=prev)&(k<prev)
            result[ix[np.asarray(up)],bull]=role
            result[ix[np.asarray(down)],bear]=role
    return result

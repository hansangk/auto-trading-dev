"""Slot statistics use only earlier observations at the same NY clock hour."""
import numpy as np
import pandas as pd
from itertools import product

FAMILIES = {'surprise':(1.25,2.),'rejection':(.70,.90),'pressure':(.75,.90),'compression':(.15,.30)}

def candidates():
    return [dict(name=f'{family}_{days}_{q}',family=family,p1=days,p2=q,hold=4,target=3,stop_bps=60)
            for family, levels in FAMILIES.items() for days,q in product((20,40),levels)]

def signals(data,times,c):
    times = pd.DatetimeIndex(times).tz_convert('America/New_York')
    scores = np.zeros_like(data.close)
    for bull,bear,role in [('TQQQ','SQQQ',1),('IBIT','BITI',-1)]:
        j = data.symbols.index(bull)
        o,h,l,k,v = [pd.Series(getattr(data,key)[:,j],index=times) for key in ('open','high','low','close','volume')]
        def history(x,q):
            return x.groupby(times.hour).transform(lambda z:z.shift().rolling(c['p1']).quantile(q))
        span=(h-l).replace(0,np.nan)
        prior_h=h.groupby(times.date).shift()
        prior_l=l.groupby(times.date).shift()
        q=c['p2']
        if c['family']=='surprise':
            ret=np.log(k/o)
            residual=ret-history(ret,.5)
            scale=(history(ret,.75)-history(ret,.25))/1.349
            direction=np.sign(residual).where((scale>0)&(residual.abs()>=q*scale),0)
        elif c['family']=='pressure':
            loc=(2*k-h-l)/span
            dollar=k*v
            direction=np.sign(loc).where((loc.abs()>=.6)&(dollar>history(dollar,q)),0)
        elif c['family']=='rejection':
            upper=(h-prior_h).clip(lower=0)/span
            lower=(prior_l-l).clip(lower=0)/span
            inside=(k<prior_h)&(k>prior_l)
            direction=((lower>history(lower,q))&inside).astype(int)-((upper>history(upper,q))&inside).astype(int)
        else:
            width=(prior_h-prior_l)/o
            direction=((k>prior_h).astype(int)-(k<prior_l).astype(int)).where(width<history(width,q),0)
        scores[direction>0,j]=role
        scores[direction<0,data.symbols.index(bear)]=role
    return scores

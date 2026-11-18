import numpy as np
import pandas as pd

def candidates():
    settings={'leader':[0],'spread':[4.6,10,25,50],'repeat':[0],'runner':[25]}
    return [dict(name=f'{family}_{value}',family=family,p1=value,p2=0,hold=4,target=3)
            for family,values in settings.items() for value in values]

def events(data,times):
    days=times.tz_convert('America/New_York').date
    for day,rows in pd.Series(np.arange(len(times))).groupby(days):
        ix=rows.to_numpy()
        if len(ix)<2:continue
        i,j=ix[:2]
        r=data.close[j]/data.open[i]-1
        order=np.argsort(-r,kind='stable')
        yield day,j,order,r,np.argmax(data.close[i]/data.open[i]-1),ix

def signals(data,times,c):
    scores=np.zeros_like(data.close)
    for day,j,order,r,prior,ix in events(data,times):
        first,second=order[:2];gap=(r[first]-r[second])*10000
        if r[first]<=0:continue
        if c['family']=='spread' and gap<c['p1']:continue
        if c['family']=='repeat' and first!=prior:continue
        pick=second if c['family']=='runner' and gap<=c['p1'] and r[second]>0 else first
        scores[j,pick]=1 if pick<2 else -1
    return scores

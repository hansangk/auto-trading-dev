"""Fixed-stratum admitted/rejected labels with whole-day bootstrap blocks."""
import numpy as np
import pandas as pd

def matched_effect(frame,all_days,draws=2000,seed=20261119):
    days=list(map(str,all_days));eligible=[]
    for key,g in frame.groupby('stratum'):
        if all(len(g[g.admit==a])>=5 and g[g.admit==a].day.nunique()>=3 for a in (0,1)):eligible.append(key)
    f=frame[frame.stratum.isin(eligible)].copy();na=int((f.admit==1).sum());nr=int((f.admit==0).sum())
    da=int(f.loc[f.admit==1,'day'].nunique());dr=int(f.loc[f.admit==0,'day'].nunique())
    result=dict(matched_events=len(f),total_events=len(frame),strata=len(eligible),admitted=na,rejected=nr,admitted_days=da,rejected_days=dr,observed_days=len(days),nonoverlap_three_day_blocks=len(days)//3,support_pass=na>=20 and nr>=20 and da>=10 and dr>=10 and len(days)//3>=6,contrast=None,day_lower=None,day_upper=None,block_lower=None,block_upper=None,day_valid_draws=0,block_valid_draws=0,information_pass=False)
    if not len(f):return result
    weights={k:len(g)/len(f) for k,g in f.groupby('stratum')};point=sum(weights[k]*(g.loc[g.admit==1,'net'].mean()-g.loc[g.admit==0,'net'].mean()) for k,g in f.groupby('stratum'));result['contrast']=float(point)
    if not result['support_pass']:return result
    rng=np.random.default_rng(seed);N=len(days);daymap={d:i for i,d in enumerate(days)};ix=f.day.map(daymap).to_numpy();assert np.isfinite(ix).all();ix=ix.astype(int)
    for mode in ('day','block'):
        if mode=='day':samples=rng.integers(0,N,size=(draws,N))
        else:
            starts=rng.integers(0,N,size=(draws,int(np.ceil(N/3))));samples=((starts[:,:,None]+np.arange(3))%N).reshape(draws,-1)[:,:N]
        counts=np.zeros((draws,N),int)
        for j in range(N):counts[:,j]=np.sum(samples==j,axis=1)
        ew=counts[:,ix];values=np.zeros(draws);valid=np.ones(draws,bool)
        for key in eligible:
            means=[]
            for a in (0,1):
                mask=((f.stratum==key)&(f.admit==a)).to_numpy();den=ew[:,mask].sum(axis=1);num=ew[:,mask]@f.loc[mask,'net'].to_numpy()
                valid &= den>0;means.append(np.divide(num,den,out=np.zeros(draws),where=den>0))
            values+=weights[key]*(means[1]-means[0])
        result[mode+'_valid_draws']=int(valid.sum())
        if valid.sum()>=.9*draws:
            result[mode+'_lower']=float(np.quantile(values[valid],.025));result[mode+'_upper']=float(np.quantile(values[valid],.975))
    result['information_pass']=bool(point>.000069 and result['block_lower'] is not None and result['block_lower']>0)
    return result

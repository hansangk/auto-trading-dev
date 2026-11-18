"""Paired event means resampled by observed NY day, including empty days."""
import numpy as np

def paired_effect(values,event_days,all_days,draws=2000,seed=20261119):
    values=np.asarray(values,float);event_days=np.asarray(event_days);days=list(all_days)
    if len(values)!=len(event_days) or not np.isfinite(values).all():raise ValueError('Finitepairedvalues/daylengthrequired')
    result=dict(events=len(values),active_days=len(set(event_days)),observed_days=len(days),support_pass=len(values)>=20 and len(set(event_days))>=10,mean=float(np.mean(values)) if len(values) else None,day_lower=None,day_upper=None,block_lower=None,block_upper=None,day_valid_draws=0,block_valid_draws=0)
    if not result['support_pass']:return result
    index={d:i for i,d in enumerate(days)}
    if not all(d in index for d in event_days):raise ValueError('Missingcalendarday')
    totals=np.zeros(len(days));counts=np.zeros(len(days))
    for value,day in zip(values,event_days):totals[index[day]]+=value;counts[index[day]]+=1
    rng=np.random.default_rng(seed);N=len(days)
    for mode in ('day','block'):
        if mode=='day':sample=rng.integers(0,N,size=(draws,N))
        else:sample=((rng.integers(0,N,size=(draws,int(np.ceil(N/3))))[:,:,None]+np.arange(3))%N).reshape(draws,-1)[:,:N]
        numerator=totals[sample].sum(axis=1);denominator=counts[sample].sum(axis=1);valid=denominator>0;result[mode+'_valid_draws']=int(valid.sum())
        if valid.sum()>=.9*draws:
            z=numerator[valid]/denominator[valid];result[mode+'_lower']=float(np.quantile(z,.025));result[mode+'_upper']=float(np.quantile(z,.975))
    return result

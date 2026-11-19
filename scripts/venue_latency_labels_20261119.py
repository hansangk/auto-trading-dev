"""Calendar support before PnL; fixed-event unprotected paths after PnL.

All exit targets use actual bar CLOSE; these are labels, not account returns.
"""
from pathlib import Path
import json
import pandas as pd,numpy as np
from venue_latency_retry_20261119 import Runner,OUT,DEV,BASE
from availability_runtime_20261119 import atomic_json
from latency_statistics_20261119 import paired_effect
from session_signal_provenance import mask_session_signals
from venue_latency_calendar_20261119 import common_mask

def support():
    from venue_isolation_retry_20261119 import Runner as Prior
    r=Prior();cal=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for c in ('open','close'):cal[c]=pd.to_datetime(cal[c],utc=True)
    rows=[]
    for arm in ('source','price'):
        score=mask_session_signals(r.score['coin__body55__'+arm],r.times,0,0,'event')
        for a,b in DEV:
            period=(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'));events=np.flatnonzero(np.any(score,axis=1)&period);groups={x:[] for x in ('all','sameexit','both4bars','original_actual_minutes_equal','minute60','minute120','minute180')}
            for i in events:
                t=r.times[i];close=cal.loc[r.days[i],'close'];e0=t+pd.Timedelta(hours=1);e1=t+pd.Timedelta(hours=2);target=min(e0+pd.Timedelta(hours=4),close);groups['all'].append(i)
                if e1<close and target>e1:groups['sameexit'].append(i)
                if e1+pd.Timedelta(hours=3)<close:groups['both4bars'].append(i)
                if e1<close and e1+(target-e0)<=close:groups['original_actual_minutes_equal'].append(i)
            for d in (60,120,180):groups['minute'+str(d)]=[i for i in events if common_mask(r.times,cal,d)[i]]
            for group,ids in groups.items():rows.append(dict(arm=arm,start=a,end_exclusive=b,group=group,events=len(ids),days=len(set(r.days[ids])),sample_pass=len(ids)>=20 and len(set(r.days[ids]))>=10,status='CALENDAR_SUPPORT_ONLY_NO_PRICE' if group!='original_actual_minutes_equal' else 'NOT_IDENTIFIED_ZERO_COMMON_SUPPORT'))
    pd.DataFrame(rows).to_csv(OUT/'calendar_support.csv',index=False);print(pd.DataFrame(rows).to_string(index=False))

def paths():
    r=Runner();cal=pd.read_csv(BASE/'calendar_schedule.csv',index_col='day')
    for c in ('open','close'):cal[c]=pd.to_datetime(cal[c],utc=True)
    label=[];summary=[]
    for arm in ('source','price'):
        s=mask_session_signals(r.score['legacy__'+arm],r.times,0,0,'event')
        for a,b in DEV:
            period=(r.times>=pd.Timestamp(a,tz='UTC'))&(r.times<pd.Timestamp(b,tz='UTC'));events=np.flatnonzero(np.any(s,axis=1)&period)
            for family in ('sameexit',60,120,180):
                records=[]
                mask=common_mask(r.times,cal,family) if isinstance(family,int) else None
                for i in events:
                    day=r.days[i];close=cal.loc[day,'close'];e0=r.times[i]+pd.Timedelta(hours=1);e1=r.times[i]+pd.Timedelta(hours=2)
                    if family=='sameexit':
                        x0=x1=min(e0+pd.Timedelta(hours=4),close)
                        if not e1<close or not x1>e1:continue
                    else:
                        if not mask[i]:continue
                        x0=e0+pd.Timedelta(minutes=family);x1=e1+pd.Timedelta(minutes=family)
                    j=int(np.flatnonzero(s[i])[0]);indices=[]
                    for target in (x0,x1):
                        start=close-pd.Timedelta(minutes=30) if target==close else target-pd.Timedelta(hours=1)
                        k=int(r.times.get_loc(start));assert start<target<=close;indices.append(k)
                    p0=r.data.open[int(r.times.get_loc(e0)),j];p1=r.data.open[int(r.times.get_loc(e1)),j];q0=r.data.close[indices[0],j];q1=r.data.close[indices[1],j]
                    base=.15*(q0/p0-1)-.000069;delayed=.15*(q1/p1-1)-.000069
                    record=dict(arm=arm,start=a,end_exclusive=b,family=str(family),signal_index=int(i),day=day,symbol=r.data.symbols[j],entry0=str(e0),entry1=str(e1),exit0=str(x0),exit1=str(x1),exit_phase='CLOSE',base_minutes=(x0-e0).total_seconds()/60,delay_minutes=(x1-e1).total_seconds()/60,base_net_label=base,delay_net_label=delayed,delta=delayed-base,NOT_account_return=True)
                    records.append(record)
                label.extend(records);q=pd.DataFrame(records);adequate=len(q)>=20 and q.day.nunique()>=10
                effect=paired_effect(q.delta.to_numpy(),q.day.to_numpy(),sorted(set(r.days[period]))) if adequate else dict(block_lower=None,block_upper=None)
                summary.append(dict(arm=arm,start=a,end_exclusive=b,family=str(family),events=len(q),days=q.day.nunique(),base_mean=q.base_net_label.mean(),delay_mean=q.delay_net_label.mean(),delta_mean=q.delta.mean(),adequate_sample=adequate,block_lower=effect['block_lower'],block_upper=effect['block_upper'],NOT_account_return=True))
    pd.DataFrame(label).to_csv(OUT/'fixed_event_paths_LOCAL.csv',index=False);pd.DataFrame(summary).to_csv(OUT/'fixed_event_path_summary.csv',index=False);print(pd.DataFrame(summary).to_string(index=False))

if __name__=='__main__':
    import sys
    if sys.argv[1:]==['support']:support()
    elif sys.argv[1:]==['paths']:paths()
    else:raise SystemExit('support/paths')

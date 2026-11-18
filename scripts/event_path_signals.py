"""Keep the previous rejection event fixed and change only direction or latency."""
import numpy as np
from slot_signals import signals as prior_signal

def candidates():
    return [dict(name=f'{side}_wait{wait}',family=side,p1=side,p2=wait,hold=4,target=3)
            for side in ('fade','continue') for wait in (0,1)]

def signals(data,times,config):
    result=prior_signal(data,times,dict(family='rejection',p1=40,p2=.9))
    if config['p1']=='continue':
        result=result[:,[1,0,3,2]].copy()
    if config['p2']:
        result=np.roll(result,1,axis=0)
        day=times.tz_convert('America/New_York').date
        result[np.r_[True,day[1:]!=day[:-1]]]=0
    return result

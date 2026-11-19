"""Frozen role interventions; never refit/rearm price/flow onsets."""
import numpy as np

SCOPES=('full','coin','sync','async')
def candidates():
    return [dict(name=f'{scope}__body{body}__{arm}',scope=scope,body=body,arm=arm) for scope in SCOPES for body in (55,35) for arm in ('source','price')]

def intervene(coin,nasdaq,scope):
    coin=np.asarray(coin);nasdaq=np.asarray(nasdaq)
    if scope not in SCOPES:raise ValueError('Unknown role scope')
    if coin.ndim!=2 or coin.shape[1]!=4 or coin.shape!=nasdaq.shape:raise ValueError('Expected common n-by4 score arrays')
    if not np.isfinite(coin).all() or not np.isfinite(nasdaq).all() or not np.isin(coin,[-1,0]).all() or not np.isin(nasdaq,[0,1]).all():raise ValueError('Invalid BUY-role scores')
    if np.any(np.sum(coin!=0,axis=1)>1) or np.any(np.sum(nasdaq!=0,axis=1)>1) or np.any((coin!=0)&(nasdaq!=0)):raise ValueError('Overlapping/ambiguous roles')
    if scope=='full':return coin+nasdaq
    if scope=='coin':return coin.copy()
    coincident=np.any(nasdaq!=0,axis=1)
    return coin*np.where(coincident if scope=='sync' else ~coincident,1,0)[:,None]

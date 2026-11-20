"""Atomic account checkpoint and fail-closed in-flight journal helpers."""
from dataclasses import asdict
from datetime import date
from pathlib import Path
import json,os,hashlib
import numpy as np
from autogrid.engine import AccountState

def clean(value):
    if isinstance(value,np.generic):return clean(value.item())
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,float) and not np.isfinite(value):return 'Infinity' if value>0 else '-Infinity' if value<0 else None
    if isinstance(value,date):return value.isoformat()
    return value

def atomic_json(path,value):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w') as f:
        json.dump(clean(value),f,indent=2,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(temp,path)

def restore_state(value):
    state=dict(value)
    if isinstance(state.get('current_date'),str):state['current_date']=date.fromisoformat(state['current_date'])
    return AccountState(**state)

def resume_state(saved,schedule,scenario,plan_hash):
    if saved['schedule']!=list(schedule) or saved['scenario']!=scenario or saved['plan_hash']!=plan_hash:
        raise RuntimeError('Monthly checkpoint provenance mismatch; no replay authorized')
    segments=saved['segments']
    if [s['selected'] for s in segments]!=list(schedule[:len(segments)]):raise RuntimeError('Monthly prefix mismatch')
    return restore_state(segments[-1]['state']) if segments else AccountState(),len(segments)

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

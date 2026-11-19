"""Storage-only amendment: verify prefix ledgers/state BEFORE month resume.

The preregistered strategy/engine code remains immutable. This launcher adds
fail-closed checks around its state restoration; it changes no signals/PnL.
"""
from pathlib import Path
from dataclasses import fields
from datetime import date
import json,os,sys
import numpy as np
import pandas as pd
from autogrid.engine import AccountState
from availability_runtime_20261119 import sha,atomic_json,restore_state

def verify_prefix(saved,out,calls,capital):
    equity=capital;peak=capital;seen=set();checked=[];required={f.name for f in fields(AccountState)}
    for index,seg in enumerate(saved['segments']):
        expected=str((pd.Timestamp('2026-01-01')+pd.DateOffset(months=index)).date())
        end=str(min(pd.Timestamp(expected)+pd.DateOffset(months=1),pd.Timestamp('2026-11-14')).date())
        ref=seg['call_ref']
        if ref in seen or not ref.startswith('new:'):raise RuntimeError('Duplicate/nonnew monthly prefix reference')
        seen.add(ref);call=calls[int(ref.split(':')[1])-1]
        if call['call_id']!=int(ref.split(':')[1]) or call['kind']!='continuous_month' or call['first_policy']!=seg['selected'] or call['scenario']!=saved['scenario'] or call['start']!=expected or call['end_exclusive']!=end or seg['month']!=expected:
            raise RuntimeError('Monthly prefix call/boundary mismatch')
        path=out/f"call_{call['call_id']}_ledger_LOCAL.jsonl"
        if not path.exists() or sha(path)!=call['ledger_sha256']:raise RuntimeError('Missing/changed prefix ledger')
        if set(seg['state'])!=required:raise RuntimeError('Incomplete AccountState prefix')
        state=restore_state(seg['state']);log=[json.loads(x) for x in path.read_text().splitlines() if x];start=equity;dd=max(0,1-equity/peak)
        if len(log)!=call['rounds']:raise RuntimeError('Prefix round count mismatch')
        for t in log:
            equity*=1+t['net_return']
            if not np.isclose(equity,t['equity'],rtol=1e-12):raise RuntimeError('Prefix trade equity mismatch')
            peak=max(peak,equity);dd=max(dd,1-equity/peak)
        if not np.isclose(state.equity,equity,rtol=1e-12) or not np.isclose(state.peak,peak,rtol=1e-12) or not np.isclose(call['total_return'],equity/start-1,atol=1e-12) or not np.isclose(call['max_drawdown'],dd,atol=1e-12):raise RuntimeError('Prefix account reconciliation mismatch')
        if state.daily_start is None or state.daily_start<=0 or state.current_date is None or not isinstance(state.current_date,date) or not expected<=state.current_date.isoformat()<end or not isinstance(state.killed,bool) or state.loss_streak<0 or not isinstance(state.cooldown_until,int):raise RuntimeError('Malformed carried risk state')
        checked.append(ref)
    return checked

def main():
    import availability_retry_20261119 as runner
    if (runner.OUT/'manifest.json').exists():raise SystemExit('Completed output protected')
    amend=json.loads((runner.OUT/'runtime_amendment.json').read_text())
    for p,h in amend['files'].items():assert sha(Path(p))==h,p
    original=runner.resume_state
    def guarded(saved,schedule,scenario,plan_hash):
        state,start=original(saved,schedule,scenario,plan_hash)
        ck=json.loads((runner.OUT/'checkpoint_LOCAL.json').read_text());checked=verify_prefix(saved,runner.OUT,ck['calls'],runner.CFG.capital)
        auditpath=runner.OUT/'prefix_resume_audit.json';audit=json.loads(auditpath.read_text()) if auditpath.exists() else []
        audit.append(dict(scenario=scenario,plan_hash=plan_hash,prefix_months=start,verified_call_refs=checked,checkpoint_sha256=sha(runner.OUT/'checkpoint_LOCAL.json')));atomic_json(auditpath,audit)
        return state,start
    runner.resume_state=guarded
    fd=os.open(runner.OUT/'RUNNING.lock',os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    try:
        try:runner.research('--pause-after-one-month' in sys.argv)
        except runner.CheckpointPause as e:print('CHECKPOINT_PAUSED:',str(e))
    finally:(runner.OUT/'RUNNING.lock').unlink()

if __name__=='__main__':main()

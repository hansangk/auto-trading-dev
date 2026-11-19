"""Readiness only. No market-price fetching, model selection or engine calls.

Calendar completion is NOT proof that input prices exist. Require full audited
sessions before terminal backtests so a partial download cannot force-close a
hold at its last row. Preserve frozen model parameters and dependency hashes.
"""
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
import csv,json,hashlib,sys

UTC=timezone.utc;NY=ZoneInfo('America/New_York')
MODELS={'h120__source':(120,2),'c180__source':(180,4)}

def timestamp(value):
    if not isinstance(value,str):raise ValueError('Timestamp must be an aware string')
    try:x=datetime.fromisoformat(value.replace(' UTC','+00:00').replace('Z','+00:00'))
    except (ValueError,TypeError) as exc:raise ValueError('Invalid timestamp') from exc
    if x.tzinfo is None:raise ValueError('Naive timestamp refused')
    return x.astimezone(UTC)

def observation_class(start,end,available,freeze,now):
    a,b,release,frozen,asof=map(timestamp,(start,end,available,freeze,now))
    if not a<b or release<b:raise ValueError('Invalid span/release order')
    if a<frozen:return 'CROSSING_FREEZE_WARMUP_ONLY' if b>frozen else 'WARMUP_ONLY'
    if b>asof:return 'INCOMPLETE_NO_LOOKAHEAD'
    if release>asof:return 'NOT_RELEASED'
    return 'POTENTIAL_NEW_OBSERVATION_NEEDS_SESSION_AND_PRICE_AUDIT'

def validate_plan(plan):
    if plan.get('real_orders')!=0 or plan.get('news_macro') is not False:raise ValueError('Scope changed')
    if len(plan['models'])!=2:raise ValueError('Frozen model set changed')
    for m in plan['models']:
        if m['name'] not in MODELS or (m['calendar_common_duration_minutes'],m['hold_eligible_bars'])!=MODELS[m['name']]:raise ValueError('Frozen timing changed')
        if (m['body_efficiency'],m['directional_taker_pressure'],m['prior_flow_mean_hours'])!=(.55,.1,4):raise ValueError('Frozen parameters changed')
    if {m['name'] for m in plan['models']}!=set(MODELS):raise ValueError('Duplicate frozen model')

def readiness(plan,calendar,now):
    validate_plan(plan);asof=timestamp(now);frozen=timestamp(plan['frozen_at_utc'])
    if asof<frozen:raise ValueError('Clock predates frozen plan')
    if not calendar:raise ValueError('No verified calendar')
    bars=[];sessions=[];seen=set()
    for row in calendar:
        day=row['day'];opened=timestamp(row['open']);closed=timestamp(row['close'])
        op,cl=opened.astimezone(NY),closed.astimezone(NY)
        if day in seen or op.date().isoformat()!=day or cl.date().isoformat()!=day:raise ValueError('Calendar date/uniqueness mismatch')
        seen.add(day)
        if op.weekday()>4 or (op.hour,op.minute)!=(9,30) or (cl.hour,cl.minute)!=(16,0) or any((op.second,op.microsecond,cl.second,cl.microsecond)) or closed-opened!=timedelta(minutes=390):raise ValueError('Normal session required; do not synthesize short day')
        starts=[opened+timedelta(hours=k) for k in range(7)]
        ends=[min(s+timedelta(hours=1),closed) for s in starts]
        bars.extend((s,e) for s,e in zip(starts,ends) if s>=frozen)
        if closed>frozen:sessions.append((day,opened,closed))
    if not sessions:raise ValueError('Calendar contains no postfreeze session')
    first=min(sessions,key=lambda x:x[1]);end=max(x[2] for x in sessions)
    count=sum(e<=asof for _,e in bars)
    expired=asof.astimezone(NY).date().isoformat()>max(seen)
    if expired:status='NEEDS_CALENDAR_EXTENSION'
    elif count==0:status='WAITING_FOR_COMPLETED_SHADOW_BARS'
    elif asof<end:status='PARTIAL_SESSION_OBSERVATIONS_ONLY_NO_TERMINAL_BACKTEST'
    else:status='CALENDAR_WINDOW_COMPLETE_INPUTS_NOT_AUDITED'
    return dict(status=status,asof_utc=asof.isoformat(),frozen_at_utc=frozen.isoformat(),verified_calendar_days=sorted(seen),expected_completed_postfreeze_ETF_bars=count,actual_fetched_ETF_rows=0,actual_fetched_source_rows=0,first_session_open_utc=first[1].isoformat(),first_possible_hour_complete_utc=(first[1]+timedelta(hours=1)).isoformat(),earliest_possible_frozen_model_decision_utc=(first[1]+timedelta(hours=2)).isoformat(),first_session_scheduled_close_utc=first[2].isoformat(),calendar_completion_not_input_access_proof=True,terminal_backtest_allowed=False,price_coverage_audit_complete=False,engine_calls=0,real_orders=0,profit_metrics=None,new_independent_validation=False)

def main():
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--calendar',required=True);p.add_argument('--now',required=True);p.add_argument('--out',required=True);p.add_argument('--plan-blob-sha1',required=True);a=p.parse_args()
    out=Path(a.out)
    if out.exists():raise RuntimeError('Existing readiness output is protected; use a new checkpoint')
    raw_plan=Path(a.plan).read_bytes();blob=hashlib.sha1(b'blob '+str(len(raw_plan)).encode()+b'\0'+raw_plan).hexdigest()
    if blob!=a.plan_blob_sha1:raise RuntimeError('Frozen plan differs from expected Git blob')
    plan=json.loads(raw_plan)
    checked={}
    for file,want in plan['code_dependency_hashes'].items():
        got=hashlib.sha256(Path(file).read_bytes()).hexdigest()
        if got!=want:raise RuntimeError('Frozen dependency mismatch: '+file)
        checked[file]=got
    for filename in ('RUNNING.lock','call_intent_LOCAL.json'):
        if (out.parent/filename).exists():raise RuntimeError('Unresolved local worker/intent; no overwrite')
    with Path(a.calendar).open() as f:calendar=list(csv.DictReader(f))
    result=readiness(plan,calendar,a.now);result.update(plan_sha256=hashlib.sha256(Path(a.plan).read_bytes()).hexdigest(),calendar_sha256=hashlib.sha256(Path(a.calendar).read_bytes()).hexdigest(),guard_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),frozen_dependency_hashes=checked)
    out.parent.mkdir(parents=True,exist_ok=True);temp=out.with_name(out.name+'.tmp');temp.write_text(json.dumps(result,indent=2)+'\n');temp.replace(out)
    print(json.dumps({k:v for k,v in result.items() if k!='frozen_dependency_hashes'},indent=2))

if __name__=='__main__':main()

"""One NEW forensic schedule/protection audit using pinned08 metadata only.
No old audit/grids, acquisition, price-based selection, engine or orders.
"""
from pathlib import Path
from datetime import timedelta,datetime,timezone
import json,hashlib
from scripts.prospective_shadow_guard_20261119 import timestamp
from scripts.prospective_execution_schedule_20261120 import plan_event,qualify_marks
OUT=Path('runs/prospective_execution_schedule_20261120_0900')
PREV=Path('runs/prospective_receipt_parity_20261120_0800')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    target=OUT/'execution_schedule_audit.json'
    if target.exists():raise RuntimeError('Completed output protected')
    if any(Path('runs').rglob('RUNNING.lock')) or any(Path('runs').rglob('call_intent_LOCAL.json')):
        raise RuntimeError('Unresolved local worker or intent')
    manifest=json.loads((PREV/'analysis_manifest.json').read_text())
    verified={}
    for group in ('artifact_sha256','frozen17_dependency_sha256','original_data_hashes','actual_input_sha256'):
        for p,w in manifest[group].items():
            if sha(p)!=w:raise ValueError('Prior08 hash changed: '+p)
            verified[p]=w
    state=json.loads(Path('RETRY_STATE.json').read_text())
    for values in state.values():
        if isinstance(values,dict):
            for p,w in values.items():
                if p.startswith('runs/') and isinstance(w,str) and len(w)==64:
                    if sha(p)!=w:raise ValueError('Trusted original/private hash changed: '+p)
                    verified[p]=w
    audit=json.loads((PREV/'receipt_parity_audit.json').read_text())
    metadata=json.loads((PREV/'verified_receipt_metadata.json').read_text())
    for p,w in metadata['sha256'].items():
        if sha(p)!=w:raise ValueError('Original metadata changed: '+p)
    mark_receipts={}
    # Published per-symbol complete-start metadata, authenticated to08's
    # parent Git blobs; no new raw/price parsing or original08 audit replay.
    per_start={}
    for p in metadata['sha256']:
        if not p.endswith('/ETF_access_manifest.json'):continue
        for item in json.loads(Path(p).read_text())['sources']:
            receipt=timestamp(item['received_host_utc'])
            for start in item['completed_starts_utc']:
                a=timestamp(start);key=(item['symbol'],a)
                per_start[key]=min(per_start.get(key,receipt),receipt)
    starts=sorted({t for _,t in per_start})
    for start in starts:
        values=[per_start[(s,start)] for s in ('TQQQ','SQQQ','IBIT','BITI')]
        end=min(start+timedelta(hours=1),timestamp('2026-11-19T21:00:00Z'))
        mark_receipts[end.isoformat()]=max(values).isoformat()
    original_trace={x['index']:x for x in audit['source_context_trace']}
    unique={}
    for r in audit['opportunity_receipt_audit']:
        key=(r['model'],r['signal_bar_start'])
        unique.setdefault(key,r)
    contract=json.loads((OUT/'preregistered_execution_schedule.json').read_text())
    rows=[]
    for (model,start),item in unique.items():
        index=int((timestamp(start)-timestamp('2026-11-19T14:30:00Z')).total_seconds()//3600)
        source_end=original_trace[index]['source_end']
        hold=2 if model=='h120' else 4
        p=plan_event(start,source_end,item['all_required_first_observed_utc'],
            '2026-11-19T14:30:00Z','2026-11-19T21:00:00Z',hold)
        base=qualify_marks(p['base_protective_marks'],mark_receipts)
        delayed=qualify_marks(p['delayed_protective_marks'],mark_receipts)
        # Contract was registered after this session. Any historic clock
        # support is FOR FORENSIC DIAGNOSIS ONLY, never a live future intent.
        p.update(model=model,base_protection_receipt_audit=base,delay1_protection_receipt_audit=delayed,
            retrospective_packet=True,prospective_after_this_plan=False,
            source_nonzero_onset=any(r['retrospective_nonzero_score'] for r in audit['opportunity_receipt_audit'] if r['model']==model and r['signal_bar_start']==start and r['arm']=='source'),
            price_nonzero_onset=any(r['retrospective_nonzero_score'] for r in audit['opportunity_receipt_audit'] if r['model']==model and r['signal_bar_start']==start and r['arm']=='price'),
            historical_bar_fill_prices_exist_in_prior_full_snapshot=True,
            independently_captured_execution_time_quotes=False,
            full_state_initialized=False,engine_calls=0,financial_metrics=None)
        rows.append(p)
    result=dict(status='CALENDAR_SCHEDULER_VERIFIED_FRESHNESS_AND_PROTECTION_REJECTED_NO_ENGINE',
        parent_commit=contract['research_parent'],verified_immutable_path_count=len(verified),
        actual08_metadata_reused=True,receipt_mapping_scope='Maximum of four ETF completed-bar first observations; not actual selected-leg fill or brokerage order evidence',
        schedule_plans=rows,
        mark_first_receipt_by_deadline=mark_receipts,
        distinct_original_event_times=len({r['event_start_utc'] for r in rows}),
        common_full_hold_support_plans=sum(r['common_full_hold_support'] for r in rows),
        primary_fresh_and_common_plans=sum(r['common_full_hold_support'] and r['source_fresh_at_receipt'] for r in rows),
        receipt_protected_common_plans=sum(r['common_full_hold_support'] and r['base_protection_receipt_audit']['all_marks_observed_by_deadline'] and r['delay1_protection_receipt_audit']['all_marks_observed_by_deadline'] for r in rows),
        historical_h120_source_onsets=sum(r['source_nonzero_onset'] for r in rows if r['model']=='h120' and r['common_full_hold_support']),
        historical_h120_price_onsets=sum(r['price_nonzero_onset'] for r in rows if r['model']=='h120' and r['common_full_hold_support']),
        interpretation='Clock path support is not an executed trade or profit. Strict actual-receipt freshness remains primary. Carried-stale event is separately labeled. Subsequent actual historical OPEN can be hypothetical evaluation price without signal lookahead, but does not prove actual receipt-protected fills. Current contract cannot be applied prospectively to Nov19.',
        new_market_requests=0,engine_calls=0,orders=0,account_trades=0,financial_metrics=None,
        AccountState_initialized=False,terminal_backtest_allowed=False,new_independent_validation=False,
        new_calendar_file=str(OUT/'calendar_20261120.csv'),new_calendar_sha256=sha(OUT/'calendar_20261120.csv'),
        prospective_next_session=dict(NY_day='2026-11-20',open_utc='2026-11-20T14:30:00Z',close_utc='2026-11-20T21:00:00Z',new_actual_ETF_rows=0,next_session_price_access_verified=False,requires_fresh_input_receipts_and_execution_quotes=True,requires_contiguous_actual_source_bridge=True),
        remaining='Need new future fresh-at-actualdecision event generation, separate frozen-carried/refresh comparator and actual protective observation timing/quotes. Do not backdate closes at nextOPEN. No engine until full horizon plus NEW FULLAccountState/modelcontrolstress integration. Existing engine AccountState is flat sessionboundary risk state only.')
    with target.open('x') as f:f.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('status','verified_immutable_path_count','distinct_original_event_times','common_full_hold_support_plans','primary_fresh_and_common_plans','receipt_protected_common_plans','historical_h120_source_onsets','historical_h120_price_onsets','engine_calls')}))
if __name__=='__main__':main()

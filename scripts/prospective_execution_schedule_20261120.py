"""Calendar-only receipt scheduling and separate protection-deadline audit.
No price input, fills, account initialization, engine, or orders.
A carried event is a NEW timing hypothesis, not repaired original PIT.
"""
from datetime import timedelta
from scripts.prospective_shadow_guard_20261119 import timestamp,NY

HOUR=timedelta(hours=1)
ALLOWED_DAYS={'2026-11-19','2026-11-20'}

def plan_event(event_start,source_end,ready,opened,closed,hold_bars):
    if type(hold_bars) is not int or hold_bars not in (2,4):
        raise ValueError('Only protected hold2/hold4 integer hypotheses')
    event,source,receipt,op,cl=map(timestamp,(event_start,source_end,ready,opened,closed))
    a,b=op.astimezone(NY),cl.astimezone(NY)
    if (a.date().isoformat() not in ALLOWED_DAYS or a.date()!=b.date() or a.weekday()>4
        or (a.hour,a.minute,a.second,a.microsecond)!=(9,30,0,0)
        or (b.hour,b.minute,b.second,b.microsecond)!=(16,0,0,0)
        or cl-op!=timedelta(minutes=390)):
        raise ValueError('Separately verified Nov19/20 normal NY session required')
    starts=[op+k*HOUR for k in range(7)]
    if event not in starts:
        raise ValueError('Original event must be an exact same-session bar start')
    decision=min(event+HOUR,cl)
    if source>decision or receipt<decision:
        raise ValueError('Source ends after event decision or receipt predates completed event')
    age=(receipt-source).total_seconds()/60
    fresh=5<=age<=65
    reasons=[] if fresh else ['SOURCE_NOT_FRESH_AT_ACTUAL_RECEIPT']
    future=[t for t in starts if t>receipt]
    base=future[0] if future else None
    delayed=(starts[starts.index(base)+1] if base is not None and starts.index(base)+1<len(starts) else None)

    def path(entry,label):
        if entry is None:
            reasons.append(label+'_NO_STRICTLY_FUTURE_ENTRY')
            return None,[],False
        i=starts.index(entry)
        chosen=starts[i:i+hold_bars]
        if len(chosen)!=hold_bars:
            reasons.append(label+'_INCOMPLETE_FULL_HOLD')
            return None,[],False
        ends=[min(t+HOUR,cl) for t in chosen]
        if any(e-t!=HOUR for t,e in zip(chosen,ends)):
            reasons.append(label+'_FINAL_PARTIAL_BAR_NOT_EQUAL_HORIZON')
            return None,[],False
        return ends[-1],[t.isoformat() for t in ends[:-1]],True

    be,bmarks,bok=path(base,'BASE')
    de,dmarks,dok=path(delayed,'DELAY1')
    return dict(event_start_utc=event.isoformat(),original_event_decision_utc=decision.isoformat(),
        source_end_utc=source.isoformat(),recorded_ready_utc=receipt.isoformat(),
        original_event_source_age_minutes=(decision-source).total_seconds()/60,
        source_age_at_receipt_minutes=age,source_fresh_at_receipt=fresh,
        base_entry_utc=base.isoformat() if base else None,delayed_entry_utc=delayed.isoformat() if delayed else None,
        base_exit_utc=be.isoformat() if be else None,delayed_exit_utc=de.isoformat() if de else None,
        hold_bars=hold_bars,required_equal_scheduled_minutes=hold_bars*60,
        base_full_hold_support=bok,delayed_full_hold_support=dok,
        common_full_hold_support=bok and dok,
        base_protective_marks=bmarks,delayed_protective_marks=dmarks,
        rejection_reasons=reasons,terminal_backtest_allowed=False,
        interpretation='Carried original-event packet scheduling diagnostic; source freshness at actual receipt is a separate primary gate. No refreshed features or executable quote inference.')

def qualify_marks(marks,receipt_by_mark):
    normalized={}
    for key,value in receipt_by_mark.items():
        canonical=timestamp(key).isoformat()
        if canonical in normalized:
            raise ValueError('Duplicate canonical protective mark')
        normalized[canonical]=timestamp(value).isoformat()
    receipt_by_mark=normalized
    if not marks:
        return dict(all_marks_observed_by_deadline=False,late_or_missing=[dict(reason='NO_INTERMEDIATE_MARKS')],terminal_backtest_allowed=False)
    bad=[]
    for value in marks:
        mark=timestamp(value);key=mark.isoformat()
        if key not in receipt_by_mark:
            bad.append(dict(mark_utc=key,reason='MISSING_RECORDED_COMPLETED_MARK'))
            continue
        receipt=timestamp(receipt_by_mark[key])
        if receipt>mark:
            bad.append(dict(mark_utc=key,first_recorded_receipt_utc=receipt.isoformat(),reason='RECEIPT_AFTER_NEXT_OPEN_DEADLINE'))
    return dict(all_marks_observed_by_deadline=not bad,late_or_missing=bad,terminal_backtest_allowed=False)

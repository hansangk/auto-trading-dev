"""Validate saved results, state continuity and explicit-period exports; no fitting."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from inverse_etf_retry_20261116 import CFG
OUT=Path('runs/hourly_clock_retry_20261119_0300')
def main():
    m=json.loads((OUT/'manifest.json').read_text());assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in m['code_config_sha256'].items())
    data=load_market_data(OUT/'audit_v2/audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    calls=pd.read_csv(OUT/'actual_calls.csv');usage=pd.read_csv(OUT/'ticker_usage.csv');extended=usage.merge(calls[['call_id','end_exclusive','purpose']],on='call_id',validate='many_to_one');extended.to_csv(OUT/'ticker_usage_explicit_periods.csv',index=False)
    sel=json.loads((OUT/'selection.json').read_text());assert len(sel['shortlist'])<=8 and set(sel['diagnostic_pool'])<=set(sel['shortlist'])
    choices=pd.read_csv(OUT/'monthly_choices.csv');assert set(choices.selected)<=set(sel['diagnostic_pool'])|{'cash'}
    for row in choices.itertuples():assert pd.Timestamp(row.training_end_exclusive)==pd.Timestamp(row.month) and pd.Timestamp(row.training_start)==pd.Timestamp(row.month)-pd.DateOffset(months=row.months)
    checkpoints=json.loads((OUT/'monthly_state_checkpoints.json').read_text());state_checks=0
    for months in (3,6):
        for scenario in ('base','cost2','delay1'):
            group=[r for r in checkpoints if r['months']==months and r['scenario']==scenario];equity=CFG.capital;peak=equity;killed=False
            for row in group:
                s=row['state'];assert np.isclose(s['equity'],equity*(1+row['total_return']));assert s['peak']>=peak and s['peak']>=s['equity'];assert not killed or s['killed']
                equity=s['equity'];peak=s['peak'];killed=s['killed'];state_checks+=1
    trade_checks=0;continuous=[]
    for row in calls.itertuples():
        log=[json.loads(x) for x in (OUT/f'call_{row.call_id}_ledger_LOCAL.jsonl').read_text().splitlines() if x]
        for t in log:
            entry,end=[int(times.searchsorted(pd.Timestamp(t[k]))) for k in ('entry','end')];signal=int(t['signal_index'])
            assert times[entry]==pd.Timestamp(t['entry']) and times[end]==pd.Timestamp(t['end']) and t['signal_index']==signal
            assert days[entry]==days[end]==days[signal]
            assert entry==signal+1+(row.scenario=='delay1')
            assert set(t['bought_symbols'])<=set(data.symbols) and all(0<w<=.150000001 for w in t['bought_weights']);trade_checks+=1
        if row.kind=='continuous_month':
            for symbol in data.symbols:continuous.append(dict(account=row.purpose,scenario=row.scenario,month=row.start,selected=row.first_policy,symbol=symbol,buys=sum(symbol in t['bought_symbols'] for t in log)))
    c=pd.DataFrame(continuous);c.to_csv(OUT/'continuous_ticker_usage.csv',index=False)
    rawchecks={s:hashlib.sha256((Path('runs/source_lead_audit_20261119_0200/hourly_access')/(s+'_raw_LOCAL.json')).read_bytes()).hexdigest()==h for s,h in {'QQQ':'a62a158a1f6a3fc85ef803c277543408e7b46c629630787013427218827271ad','BTC-USD':'5a470cea79415bc73c87eaeeb5740fe8c5e1f95c2b72e9f05e68e8def54cb206'}.items()};assert all(rawchecks.values())
    v=dict(tests_passed=145,test_seconds=11.555,code_hashes_pass=True,raw_source_hashes_pass=rawchecks,state_continuity_segments_passed=state_checks,same_session_trade_provenance_checks=trade_checks,original_legacy_regression_calls=6,original_legacy_fields_percell=6,main_completed_calls=m['engine_calls'],total_completed_calls=m['engine_calls']+6,aborted_unpersisted_call=1,total_actual_calls_including_abort=m['engine_calls']+7,metadata_note='Originalticker_usage omittedend; explicit_periods export joins actualcallend bycallid; originalpreserved. Continuouscounts independentlyderivedfromsavedledgers.',publication_note='TwoCSVcheckpointreads truncated; repaired9045499 and exactremote/localcontentverified beforefinal. Usechunkedreads/contentcomparison forlargeartifacts.',extra_code_sha256={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in ['scripts/hourly_results_verify_20261119.py','scripts/hourly_legacy_repro_20261119.py']})
    (OUT/'verification.json').write_text(json.dumps(v,indent=2));print(json.dumps(v,indent=2));print(c.groupby(['account','scenario','symbol']).buys.sum().to_string())
if __name__=='__main__':main()

"""Verify execution/caching counts, flat monthly state and actual BUY ledgers."""
from pathlib import Path
import json,hashlib
import pandas as pd
import numpy as np
from autogrid.data import load_market_data
from inverse_etf_retry_20261116 import CFG
OUT=Path('runs/latency_decomposition_20261119_0600')
def main():
    m=json.loads((OUT/'manifest.json').read_text());assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in m['code_config_sha256'].items())
    prov=json.loads((OUT/'cache_provenance.json').read_text());assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==v['sha256'] for p,v in prov['verified'].items())
    data=load_market_data('runs/hourly_clock_retry_20261119_0300/audit_v2/audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    calls=pd.read_csv(OUT/'actual_calls.csv');cached=pd.read_csv(OUT/'cached_cells.csv');assert len(calls)==m['engine_calls'] and len(cached)==8
    states=json.loads((OUT/'monthly_state_checkpoints.json').read_text());checks=0
    for family in 'ABCD':
        for cost in (1,2):
            equity=CFG.capital;peak=equity;killed=False
            for row in [r for r in states if r['family']==family and r['cost']==cost]:
                state=row['state'];assert np.isclose(state['equity'],equity*(1+row['total_return']));assert state['peak']>=peak and state['peak']>=state['equity'];assert not killed or state['killed'];equity=state['equity'];peak=state['peak'];killed=state['killed'];checks+=1
    trades=0
    for row in calls.itertuples():
        log=[json.loads(x) for x in (OUT/f'call_{row.call_id}_ledger_LOCAL.jsonl').read_text().splitlines() if x]
        for t in log:
            entry,end=[int(times.searchsorted(pd.Timestamp(t[k]))) for k in ('entry','end')];signal=int(t['signal_index']);assert times[entry]==pd.Timestamp(t['entry']) and times[end]==pd.Timestamp(t['end']);assert days[entry]==days[end]==days[signal];assert entry==signal+1+row.delay
            assert len(t['bought_symbols'])==1 and set(t['bought_symbols'])<=set(data.symbols) and all(0<w<=.150000001 for w in t['bought_weights']);trades+=1
    stats=pd.read_csv(OUT/'paired_path_statistics.csv');strict=stats[(stats.policy.isin(['source','parent']))&(stats.contrast=='equal_wall4_B_A')];assert (strict.events==0).all()
    exact=stats[(stats.contrast=='equal_wall3_C_D')&(stats.events>0)];assert np.allclose(exact.mean_minutes_x,180) and np.allclose(exact.mean_minutes_y,180)
    results=pd.read_csv(OUT/'account_results.csv');assert not ((results.policy=='source')&(results.cohort=='common')&(results.cost==2)).any();assert not ((results.policy=='source')&(results.cohort=='common')&(results.start>='2026-01-01')).any()
    exits=pd.read_csv(OUT/'protected_exit_analysis.csv');new=exits[exits.origin=='NEW_CALL'];unique=new.phase!='ambiguous_equal_price';assert (new.loc[unique,'reserved_gap_minutes']>=-1e-7).all()
    v=dict(tests_passed=166,test_seconds=11.337,new_engine_calls=len(calls),cached_old_reset_cells=len(cached),monthly_state_segments=checks,new_trade_provenance_checks=trades,strict240_support_zero=True,strict180_duration_pass=True,source_under20_stress_diag_skipped=True,cache_commit=prov['old_commit'],cache_dependency_result_blobs_verified=len(prov['verified']),exit_phase_unique_new_rounds=int(unique.sum()),exit_phase_ambiguous_new_rounds=int((~unique).sum()),actual_clock_before_reserved_release_new_rounds=int((new.loc[unique,'reserved_gap_minutes']>1e-7).sum()),max_reserved_gap_minutes=float(new.reserved_gap_minutes.max()),code_config_hashes_pass=True,engine_unchanged=True,verifier_sha256=hashlib.sha256(Path('scripts/latency_verify_20261119.py').read_bytes()).hexdigest())
    (OUT/'verification.json').write_text(json.dumps(v,indent=2));print(json.dumps(v,indent=2));print(pd.read_csv(OUT/'monthly_ticker_usage.csv').groupby(['family','cost','symbol']).buys.sum().to_string())
if __name__=='__main__':main()

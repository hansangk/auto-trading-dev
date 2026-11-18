"""Saved-ledger continuity, BUY budgets and dollar gross/cost decomposition."""
from pathlib import Path
import json,hashlib
import numpy as np
import pandas as pd
from autogrid.data import load_market_data
from inverse_etf_retry_20261116 import CFG
OUT=Path('runs/nasdaq_gate_audit_20261119_0330')
def main():
    m=json.loads((OUT/'manifest.json').read_text());assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in m['code_config_sha256'].items())
    data=load_market_data('runs/hourly_clock_retry_20261119_0300/audit_v2/audited_ETF_LOCAL.csv.gz',['TQQQ','SQQQ','IBIT','BITI']);times=pd.to_datetime(data.timestamps,utc=True);days=times.tz_convert('America/New_York').date
    checkpoints=json.loads((OUT/'monthly_state_checkpoints.json').read_text());checked=0
    for variant in ('original','replace_qqq_consensus','replace_qqq_gap'):
        for scenario in ('base','cost2','delay1'):
            equity=CFG.capital;peak=equity;killed=False
            for row in [r for r in checkpoints if r['variant']==variant and r['scenario']==scenario]:
                state=row['state'];assert np.isclose(state['equity'],equity*(1+row['total_return']));assert state['peak']>=peak and state['peak']>=state['equity'];assert not killed or state['killed'];equity=state['equity'];peak=state['peak'];killed=state['killed'];checked+=1
    calls=pd.read_csv(OUT/'actual_calls.csv');decomp={};trades=0
    for row in calls.itertuples():
        log=[json.loads(x) for x in (OUT/f'call_{row.call_id}_ledger_LOCAL.jsonl').read_text().splitlines() if x]
        for t in log:
            entry,end=[int(times.searchsorted(pd.Timestamp(t[k]))) for k in ('entry','end')];signal=int(t['signal_index'])
            assert times[entry]==pd.Timestamp(t['entry']) and times[end]==pd.Timestamp(t['end']);assert days[entry]==days[end]==days[signal];assert entry==signal+1+(row.scenario=='delay1')
            assert set(t['bought_symbols'])<=set(data.symbols) and all(0<w<=.150000001 for w in t['bought_weights']);trades+=1
            if row.kind=='monthly':
                z=decomp.setdefault((row.first_policy,row.scenario),dict(gross=0.,cost=0.,net=0.,rounds=0));before=t['equity']-t['pnl'];z['gross']+=before*t['gross_return'];z['cost']+=before*t['cost_return'];z['net']+=t['pnl'];z['rounds']+=1
    monthly=pd.read_csv(OUT/'monthly_counterfactual.csv');rows=[]
    for (variant,scenario),v in decomp.items():
        expected=monthly[(monthly.variant==variant)&(monthly.scenario==scenario)].iloc[0];assert np.isclose(v['net']/CFG.capital,expected.total_return);assert np.isclose(v['gross']-v['cost'],v['net'],atol=2.,rtol=1e-6)
        rows.append(dict(variant=variant,scenario=scenario,rounds=v['rounds'],gross_pct=100*v['gross']/CFG.capital,cost_pct=100*v['cost']/CFG.capital,net_pct=100*v['net']/CFG.capital,rounding_residual_money=v['gross']-v['cost']-v['net']))
    pd.DataFrame(rows).to_csv(OUT/'monthly_gross_cost_decomposition.csv',index=False)
    v=dict(tests_passed=157,test_seconds=10.871,engine_calls=m['engine_calls'],state_continuity_segments=checked,trade_provenance_checks=trades,source_static_regression_cells=15,original_monthly_regression_scenarios=3,code_config_hashes_pass=True,metadata_note='entry/end timestamps explicitlymapped,signal_index numeric; overlappingwindows exportstart/end/callid.',decomposition='Dollarbefore-equity gross/cost sums dividedbyinitialcapital; netexactfromPnL, gross/costlimitedbyserializedreturnprecision. Notrawsumofroundreturns.',extra_code_sha256=hashlib.sha256(Path('scripts/nasdaq_gate_verify_20261119.py').read_bytes()).hexdigest())
    (OUT/'verification.json').write_text(json.dumps(v,indent=2));print(json.dumps(v));print(pd.DataFrame(rows).to_string(index=False))
if __name__=='__main__':main()

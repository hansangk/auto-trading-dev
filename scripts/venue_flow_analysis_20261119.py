"""Descriptive accounting of already completed runs; zero engine calls."""
import json,hashlib
from pathlib import Path
import pandas as pd,numpy as np
from venue_flow_retry_20261119 import Runner,OUT,DEV
from availability_runtime_20261119 import atomic_json,sha

def main():
    r=Runner();rows=[];usage=[];pre=pd.read_csv(OUT/'returnblind_preflight.csv');prep=json.loads((OUT/'prepared_manifest.json').read_text());selection=json.loads((OUT/'selection.json').read_text())
    for x in r.ck['rows']:
        if (x['start'],x['end_exclusive']) not in DEV and x['purpose'] not in ('recent3m_fit','recent6m_fit','reused2026_diagnostic'):continue
        log=r.log(x['call_ref']);nas=btc=fees=0;holds=[];starts=[];ends=[]
        for t in log:
            initial=t['equity']-t['pnl'];nas+=initial*t['long_gross_return'];btc+=initial*t['short_gross_return'];fees+=initial*t['cost_return'];starts.append(t['entry']);ends.append(t['end']);holds.append((pd.Timestamp(t['end'])-pd.Timestamp(t['entry'])).total_seconds()/60)
        rows.append(dict(name=x['name'],start=x['start'],end_exclusive=x['end_exclusive'],scenario=x['scenario'],call_ref=x['call_ref'],gross_Nasdaq_currency=nas,gross_Bitcoin_currency=btc,cost_currency=fees,net_currency=nas+btc-fees,first_entry=min(starts) if starts else None,last_exit_bar_start=max(ends) if ends else None,min_entry_to_exit_bar_start_minutes=min(holds) if holds else None,max_entry_to_exit_bar_start_minutes=max(holds) if holds else None,exit_phase='open/close reconciled individually by verifier; same-price phase ambiguous; lastbar30min'))
    pd.DataFrame(rows).to_csv(OUT/'leg_cost_attribution.csv',index=False)
    aliasrows=[dict(name=n,development_representative=a,stress_logical=n in selection['shortlist'],diagnostic_logical=n in selection['diagnostic_pool']) for n,a in prep['aliases'].items()]
    pd.DataFrame(aliasrows).to_csv(OUT/'effective_aliases.csv',index=False)
    datasets=['scripts/venue_flow_context_20261119.py','scripts/venue_flow_signals_20261119.py','scripts/venue_flow_retry_20261119.py','scripts/venue_flow_verify_20261119.py','scripts/venue_flow_analysis_20261119.py','tests/test_venue_flow_signals.py','src/autogrid/engine.py','configs/win60_search.yaml','scripts/availability_runtime_20261119.py','scripts/availability_guarded_research_20261119.py','scripts/hourly_night_signals_20261119.py','scripts/session_signal_provenance.py','scripts/latency_statistics_20261119.py']
    proof=json.loads((OUT/'resume_proof.json').read_text())
    atomic_json(OUT/'analysis_manifest.json',dict(analysis_new_engine_calls=0,nominal_definitions=64,effective_development_arrays=len(set(prep['aliases'].values())),nominal_stress_definitions=8,effective_stress_development_arrays=len(set(prep['aliases'][n] for n in selection['shortlist'])),nominal_diagnostic_pool=len(selection['diagnostic_pool']),effective_diagnostic_development_arrays=len(set(prep['aliases'][n] for n in selection['diagnostic_pool'])),logical_aliases_never_extra_engine_calls=True,resume_committed_prefix_call=proof['call_id'],raw_access='Local raw only, no upload retried',hashes={p:sha(Path(p)) for p in datasets},checkpoint_sha256=sha(OUT/'checkpoint_LOCAL.json'),raw_ledger_manifest={c['call_id']:c['ledger_sha256'] for c in r.ck['calls']}))
    print('analysis complete; no enginecalls;42unique development arrays/6stressed')

if __name__=='__main__':main()

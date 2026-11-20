"""Fail closed around the immutable executed runner's continuation boundary.

The completed experiment's original code/hash is preserved. Its reset cells
checkpoint exactly, but a partial continuous schedule does NOT persist enough
AccountState to authorize an automatic restart. Never repeat it silently.
"""
from pathlib import Path
import json,subprocess,sys

OUT=Path('runs/source_activity_grid_20261119_0700')

def validate_resume(out,phase):
    if phase not in ('development','research'):raise ValueError('Unknown execution phase')
    if (out/'manifest.json').exists():raise RuntimeError('COMPLETE: do not rerun; use source_activity_verify_20261119.py')
    if (out/'RUNNING.lock').exists():raise RuntimeError('RUNNING lock: do not duplicate or clear it')
    if not (out/'preregistered_plan.json').exists():raise RuntimeError('Missing preregistered plan')
    if phase=='development' and (out/'selection.json').exists():raise RuntimeError('Development complete; do not repeat')
    if phase=='research':
        if not (out/'selection.json').exists():raise RuntimeError('Missing frozen development selection')
        path=out/'execution_checkpoint_LOCAL.json';checkpoint=json.loads(path.read_text()) if path.exists() else {}
        if any(c.get('kind')=='continuous_month' for c in checkpoint.get('calls',[])):
            raise RuntimeError('PARTIAL_CONTINUOUS: exact carried month state must be recovered and verified; automatic prefix replay forbidden')
    return True

if __name__=='__main__':
    if len(sys.argv)!=2:raise SystemExit('Use development/research after remote ownership check')
    try:validate_resume(OUT,sys.argv[1])
    except (RuntimeError,ValueError) as e:raise SystemExit(str(e))
    subprocess.run([sys.executable,'scripts/source_activity_retry_20261119.py',sys.argv[1]],check=True)

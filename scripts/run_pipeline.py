import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

steps = [
    [sys.executable, str(ROOT / 'scripts' / '01_clean_data.py')],
    [sys.executable, str(ROOT / 'scripts' / '02_validate_data.py')],
    [sys.executable, str(ROOT / 'scripts' / '03_build_master_data.py')],
    [sys.executable, str(ROOT / 'scripts' / '04_create_features.py')],
]

print('Running MPLAD Sentinel pipeline...')
for idx, step in enumerate(steps, start=1):
    print(f'[{idx}/4] Running step {idx}')
    result = subprocess.run(step, cwd=str(ROOT), capture_output=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)

print('Pipeline completed successfully.')

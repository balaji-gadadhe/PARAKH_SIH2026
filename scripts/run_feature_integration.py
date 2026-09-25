"""
Root forwarding runner for Feature Integration Pipeline.
Allows running `python scripts/run_feature_integration.py` from repository root.
"""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "ml_features"
RUNNER = ML_DIR / "scripts" / "run_feature_integration.py"

if __name__ == "__main__":
    cmd = [sys.executable, str(RUNNER)] + sys.argv[1:]
    res = subprocess.run(cmd, cwd=str(ML_DIR))
    sys.exit(res.returncode)

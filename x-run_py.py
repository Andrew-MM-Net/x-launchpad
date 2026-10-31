# run_py.py - run app.py with its venv (.venv first, then venv). Stdlib only.
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "app.py"

for name in (".venv", "venv"):
    py = HERE / name / "Scripts" / "python.exe"
    if py.exists():
        break
else:
    sys.exit(f"No venv found: looked for .venv and venv in {HERE}")

if not SCRIPT.exists():
    sys.exit(f"Script not found: {SCRIPT}")

sys.exit(subprocess.call([str(py), str(SCRIPT), *sys.argv[1:]], cwd=HERE))

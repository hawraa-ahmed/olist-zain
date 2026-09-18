"""
Run the whole pipeline in order. From the project root:  python run_all.py

Steps:
  1. cleaning/verify_cleaning.py   checks data/cleaned/ against data/raw/
  2. analysis/01_delivery.py
  3. analysis/02_sellers.py
  4. analysis/03_freight.py
  5. verify/verify_results.py      independent recomputation of every headline
  6. tools/make_notebooks.py       rebuilds the executed notebooks

Stops at the first failure. Pass --skip-notebooks to leave step 6 out.
"""

import subprocess
import sys

STEPS = [
    ["python", "cleaning/verify_cleaning.py"],
    ["python", "analysis/01_delivery.py"],
    ["python", "analysis/02_sellers.py"],
    ["python", "analysis/03_freight.py"],
    ["python", "verify/verify_results.py"],
]
if "--skip-notebooks" not in sys.argv:
    STEPS.append(["python", "tools/make_notebooks.py"])

for step in STEPS:
    print("\n" + "=" * 72)
    print("RUNNING:", " ".join(step))
    print("=" * 72)
    result = subprocess.run(step)
    if result.returncode != 0:
        print(f"\nSTOPPED: {' '.join(step)} exited with code {result.returncode}")
        sys.exit(result.returncode)

print("\nAll steps completed.")

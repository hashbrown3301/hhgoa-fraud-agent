"""Patch the 20 answer files to reflect that write_back.py already succeeded."""
import json
from pathlib import Path
from agent.schema import validate, Reference
import pandas as pd

cp = pd.read_csv("data/case_pack.csv")

for path in sorted(Path("cases").glob("HHG-*.json")):
    ans = json.loads(path.read_text(encoding="utf-8"))
    ans["case"]["written_to_graph"] = True
    ans["case"]["graph_case_id"] = ans["case_id"]
    path.write_text(json.dumps(ans, indent=2, ensure_ascii=False), encoding="utf-8")

print("Patched all files. Re-validating...")
errs_total = 0
for path in sorted(Path("cases").glob("HHG-*.json")):
    ans = json.loads(path.read_text(encoding="utf-8"))
    errs, warns = validate(ans)
    if errs:
        errs_total += 1
        print(path.name, "ERRORS:", errs)
print(f"{'All still valid' if errs_total == 0 else f'{errs_total} files broke'}")
"""Precompute BOTH possible customer-reply branches for every uncertain case, so the UI
can toggle between them instantly with no live computation. Adds a top-level "what_if"
block to each answer file: {"confirms": {...}, "denies": {...}} each shaped like the
existing next_best_actions/verdict/probability, built the same way build_answer.py does.
Run AFTER build_answer.py (needs the same facts). Safe to re-run.
"""
import json
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from pathlib import Path
from agent.detectors import load_transactions, customer_history, gather_facts, add_profile
from agent.memory import CaseMemory
from agent.assess import assess
from agent.actions import initial_actions, final_actions, connected

cases = pd.read_csv("data/case_pack.csv").set_index("case_id")
cc = pd.read_csv("data/closed_cases_history.csv")
mem = CaseMemory(df=cc)
tx = load_transactions("data/slice_customers_noV.csv")
dev_light = pd.read_csv("data/slice_devices.csv", low_memory=False)
dev_light["ts"] = pd.to_datetime(dev_light["ts"])
dev_light = add_profile(dev_light)


def branch(f, a0, trigger, reply):
    a1 = assess(f, trigger, mem, None, reply=reply)
    acts = final_actions(a0, a1, f, trigger, reply)
    return {
        "reply": reply,
        "probability": a1["probability"],
        "verdict": a1["verdict"],
        "pattern": a1["pattern"],
        "actions": acts,
        "explanation": a1["rule"],
    }


count = 0
for path in sorted(Path("cases").glob("HHG-*.json")):
    ans = json.loads(path.read_text(encoding="utf-8"))
    case_id = ans["case_id"]
    if not ans["evidence_requests"]:
        continue  # nothing was asked, so there's no branch to simulate
    r = cases.loc[case_id]
    hist = customer_history(tx, r["customer_id"], r["opened_at"])
    f = gather_facts(hist, r["flagged_txn_id"], dev_light, as_of=r["opened_at"])
    a0 = assess(f, r["trigger_type"], mem, r["opened_at"])

    ans["what_if"] = {
        "confirms": branch(f, a0, r["trigger_type"], "confirms"),
        "denies": branch(f, a0, r["trigger_type"], "denies"),
        "actual_reply": ans["evidence_requests"][0].get("assumed_response", ""),
    }
    path.write_text(json.dumps(ans, indent=2, ensure_ascii=False), encoding="utf-8")
    count += 1

print(f"Added what_if branches to {count} cases (the rest had no evidence request).")
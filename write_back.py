"""Write each of the 20 answer files' case results back into TigerGraph as FraudCase
vertices, linked to the customer, card, affected transactions, and any cited closed cases.
Run AFTER build_answer.py. Run from the hhgoa folder: python write_back.py
"""
import json
from pathlib import Path
import pandas as pd
from agent.tools import write_fraud_case, link_case

cases = pd.read_csv("data/case_pack.csv").set_index("case_id")

for path in sorted(Path("cases").glob("HHG-*.json")):
    ans = json.loads(path.read_text(encoding="utf-8"))
    case_id, c = ans["case_id"], ans["case"]
    r = cases.loc[case_id]

    attrs = {
        "status": c["status"], "verdict": c["verdict"],
        "fraud_probability": c["fraud_probability"], "pattern": c["pattern"],
        "pattern_description": c["pattern_description"], "exposure_usd": c["exposure_usd"],
        "summary": c["summary"], "stop_reason": ans["stop_reason"],
        "opened_at": str(r["opened_at"]), "trigger_type": r["trigger_type"],
    }
    print(f"{case_id}: writing FraudCase...", end=" ")
    res = write_fraud_case(case_id, attrs)
    ok = isinstance(res, dict) and res is not None
    print("ok" if ok else res)

    link_case(case_id, "INVOLVES", "Customer", r["customer_id"])
    card_id = r["customer_id"]  # Card.id == customer_id in our schema simplification
    link_case(case_id, "INVOLVES_CARD", "Card", card_id)

    for txn_id in c["affected_txn_ids"]:
        link_case(case_id, "ABOUT_TXN", "Txn", str(txn_id))

    for closed_id in c["similar_prior_cases"]:
        link_case(case_id, "SIMILAR_TO", "ClosedCase", closed_id, attributes={"similarity": 0.0})

    print(f"  linked: customer, card, {len(c['affected_txn_ids'])} txns, "
          f"{len(c['similar_prior_cases'])} similar cases")

print("\nDone. Verify with: python -c \"from agent.tools import call_tool; "
      "print(call_tool('get_vertex_count', vertex_type='FraudCase'))\"")
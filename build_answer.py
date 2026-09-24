"""Assemble the 20 answer JSON files from the full pipeline (detectors -> assess -> actions
-> sar -> LLM-written summary/narrative, grounded in the same facts) and validate every one.
Run from the hhgoa folder: `python build_answer.py`
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from agent.detectors import load_transactions, customer_history, gather_facts, add_profile
from agent.memory import CaseMemory
from agent.actions import plan_case
from agent.sar import build_sar
from agent.narrate import llm_summary, llm_sar_narrative
from agent.schema import new_answer, evidence as ev, write_answer, validate, Reference
from agent.tracer import Tracer

STATUS_MAP = {"fraud": "closed_fraud", "legitimate": "closed_legitimate", "uncertain": "escalated"}


def build_card_lookup(cc, cp):
    lookup = {}
    for df in (cc, cp):
        for c, k in zip(df["customer_id"], df["card_id"]):
            lookup.setdefault(c, set()).add(k)
    return {k: sorted(v) for k, v in lookup.items()}


def make_evidence(a):
    out = []
    for key, e in a["evidence_for"].items():
        out.append(ev(e["claim"], "graph", f"detector:{key}", e.get("entity_ids") or []))
    for name, claim in a["evidence_against"].items():
        out.append(ev(claim, "graph", f"counter:{name}", []))
    if a.get("customer_denial"):
        out.append(ev("Cardholder was asked and denied making the transaction(s)", "customer", "evidence_request:1", []))
    if not out:
        out.append(ev("No deviation found from this card's established behaviour", "graph", "detector:baseline", []))
    return out


def facts_for_llm(r, a, p, exposure):
    """Compact, curated fact set passed to the LLM - nothing here is invented; every
    field traces back to detectors.py/assess.py/actions.py output."""
    return {
        "case_id": r["case_id"], "customer_id": r["customer_id"], "card_id": r["card_id"],
        "trigger_type": r["trigger_type"], "verdict": a["verdict"], "pattern": a["pattern"],
        "pattern_description": a["pattern_description"], "fraud_probability": a["probability"],
        "rule_applied": a["rule"], "exposure_usd": exposure,
        "affected_txn_count": len(a["episode_txn_ids"]),
        "evidence_for": [e["claim"] for e in a["evidence_for"].values()],
        "evidence_against": list(a["evidence_against"].values()),
        "customer_denial": a["customer_denial"],
        "connected_customers": p["connected"]["customers"],
        "precedent_cases": (a["precedent"]["cases"] if a.get("precedent") else []),
        "final_actions": [x["action"] for x in p["final"]],
        "stop_reason": a["stop_reason"] or a["rule"],
    }


def main():
    cases = pd.read_csv("data/case_pack.csv")
    cc = pd.read_csv("data/closed_cases_history.csv")
    lookup = build_card_lookup(cc, cases)
    mem = CaseMemory(df=cc)

    tx = load_transactions("data/slice_customers_noV.csv")
    dev_light = pd.read_csv("data/slice_devices.csv", low_memory=False)
    dev_light["ts"] = pd.to_datetime(dev_light["ts"])
    dev_light = add_profile(dev_light)

    ref = Reference(txn_amounts=dict(zip(tx["txn"], tx["TransactionAmt"])),
                    case_ids=set(cases["case_id"]))

    results = []
    for _, r in cases.iterrows():
        t = Tracer(r["case_id"])
        hist = customer_history(tx, r["customer_id"], r["opened_at"])
        t.tool("customer_history", customer_id=r["customer_id"])
        f = gather_facts(hist, r["flagged_txn_id"], dev_light, as_of=r["opened_at"])
        t.tool("gather_facts", txn=str(r["flagged_txn_id"]))
        p = plan_case(f, r["trigger_type"], mem, r["opened_at"], lookup)
        t.tool("case_memory.similar")
        if p["evidence_requests"]:
            t.tool("simulate_reply")

        a = p["a1"]
        link = "cross_card_link" in a["evidence_for"]
        undoc = a["pattern"] == "undocumented"
        exposure = round(a["exposure_usd"], 2) if a["verdict"] == "fraud" else 0.0

        sar = build_sar(r["case_id"], r["customer_id"], r["card_id"], f, a, p, link, undoc)

        facts = facts_for_llm(r, a, p, exposure)
        fallback_summary = (f"{a['pattern'].replace('_',' ').title() if a['pattern']!='none' else 'No fraud pattern'} "
                            f"assessed at p={a['probability']:.2f} ({a['rule']}).")
        summary_text, sum_tokens = llm_summary(facts, fallback_summary)
        t.llm("summary", sum_tokens)

        if sar["file"]:
            narrative_text, sar_tokens = llm_sar_narrative(facts, sar["narrative"])
            sar["narrative"] = narrative_text
            t.llm("sar_narrative", sar_tokens)

        ans = new_answer(r["case_id"])
        aff = list(a["episode_txn_ids"]) if a["verdict"] == "fraud" else []
        first = a["first_txn_id"] if aff else ""
        ans["case"].update(
            status=STATUS_MAP[a["verdict"]],
            verdict=a["verdict"],
            fraud_probability=a["probability"],
            pattern=a["pattern"] if a["verdict"] != "legitimate" else "none",
            pattern_description=a["pattern_description"] if a["pattern"] == "undocumented" else "",
            affected_txn_ids=aff,
            first_suspicious_txn_id=first,
            connected_card_ids=(p["connected"]["cards"] if link else []),
            connected_device_profiles=([f["device"]["profile"]] if (link and f["device"]["profile"]) else []),
            exposure_usd=exposure,
            evidence=make_evidence(a),
            similar_prior_cases=(a["precedent"]["cases"][:4] if a.get("precedent") else []),
            summary=summary_text,
            written_to_graph=False, graph_case_id="",
        )
        ans["evidence_requests"] = p["evidence_requests"]
        ans["next_best_actions"] = {"initial": p["initial"], "final": p["final"], "what_changed": p["what_changed"]}
        ans["sar"] = sar
        ans["stop_reason"] = a["stop_reason"] or a["rule"]
        stats = t.stats()
        ans.update(tool_calls=stats["tool_calls"], tokens=stats["tokens"], latency_s=stats["latency_s"])

        errs, warns = validate(ans, ref)
        path = write_answer(ans)
        t.save()
        results.append((r["case_id"], errs, warns, path))

    ok = 0
    for cid, errs, warns, path in results:
        status = "OK  " if not errs else "FAIL"
        ok += not errs
        print(f"{status} {cid} -> {path}  errors={len(errs)} warnings={len(warns)}")
        for e in errs:
            print("    ERROR:", e)
        for w in warns:
            print("    warn :", w)
    print(f"\n{ok}/{len(results)} valid")


if __name__ == "__main__":
    main()
"""Answer-file builder + validator for the HHGOA fraud task.

validate(answer, ref=None) -> (errors, warnings)
  errors   = would break the README format or policy (fix before submitting)
  warnings = suspicious but not provably wrong
"""
import json
import re
from pathlib import Path

try:                                   # works both as agent.schema and plain schema
    from .policy import ALL_ACTIONS, route, CASE_MIN_PROB
except ImportError:
    from policy import ALL_ACTIONS, route, CASE_MIN_PROB

STATUS = {"open", "closed_fraud", "closed_legitimate", "escalated"}
VERDICT = {"fraud", "legitimate", "uncertain"}
PATTERNS = {"card_testing", "card_not_present_fraud", "card_not_present_new_device",
            "out_of_region_use", "account_takeover", "undocumented", "none"}
EVIDENCE_SOURCES = {"graph", "document", "customer", "external"}
REQUEST_TYPES = {"customer_validation", "step_up_auth", "analyst_info"}
ROUTES = {"auto", "L1", "L2"}

TOP_KEYS = ["case_id", "case", "evidence_requests", "next_best_actions", "sar",
            "stop_reason", "tool_calls", "tokens", "latency_s"]
CASE_KEYS = ["status", "verdict", "fraud_probability", "pattern", "pattern_description",
             "affected_txn_ids", "first_suspicious_txn_id", "connected_card_ids",
             "connected_device_profiles", "exposure_usd", "evidence", "similar_prior_cases",
             "summary", "written_to_graph", "graph_case_id"]
SAR_KEYS = ["file", "reason", "narrative", "subjects", "total_amount_usd", "activity_dates"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CARD_RE = re.compile(r"^C\d{5}-K\d+$")


# ------------------------------------------------------------------ builders
def new_answer(case_id):
    """Skeleton with every required field present, so nothing is ever missing."""
    return {
        "case_id": case_id,
        "case": {
            "status": "open", "verdict": "uncertain", "fraud_probability": 0.5,
            "pattern": "none", "pattern_description": "",
            "affected_txn_ids": [], "first_suspicious_txn_id": "",
            "connected_card_ids": [], "connected_device_profiles": [],
            "exposure_usd": 0.0, "evidence": [], "similar_prior_cases": [],
            "summary": "", "written_to_graph": False, "graph_case_id": "",
        },
        "evidence_requests": [],
        "next_best_actions": {"initial": [], "final": [], "what_changed": "nothing"},
        "sar": no_sar("No report required."),
        "stop_reason": "", "tool_calls": 0, "tokens": 0, "latency_s": 0.0,
    }


def no_sar(reason):
    return {"file": False, "reason": reason, "narrative": "", "subjects": [],
            "total_amount_usd": 0, "activity_dates": []}


def action(name, reason, exposure=0.0):
    """One recommended action; the route always comes from policy, never typed by hand."""
    return {"action": name, "route": route(name, exposure), "reason": reason}


def evidence(claim, source, ref, entity_ids=None):
    return {"claim": claim, "source": source, "ref": ref, "entity_ids": list(entity_ids or [])}


def evidence_request(rtype, asked_after_step, assumed_response):
    return {"type": rtype, "asked_after_step": int(asked_after_step),
            "assumed_response": assumed_response}


def write_answer(answer, out_dir="cases"):
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"{answer['case_id']}.json"
    path.write_text(json.dumps(answer, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# ------------------------------------------------------------------ reference data
class Reference:
    """Optional dataset facts for ID / exposure checks.
    txn_amounts: {"3514030": 77.07, ...}   (string ids -> TransactionAmt)
    card_ids / closed_case_ids: sets of strings from the dataset files."""
    def __init__(self, txn_amounts=None, card_ids=None, closed_case_ids=None, case_ids=None):
        self.txn_amounts = {str(k): float(v) for k, v in (txn_amounts or {}).items()}
        self.card_ids = set(card_ids or [])
        self.closed_case_ids = set(closed_case_ids or [])
        self.case_ids = set(case_ids or [])


# ------------------------------------------------------------------ validator
def _is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _actions(errs, actions, label, exposure):
    if not isinstance(actions, list):
        errs.append(f"{label}: must be a list")
        return []
    names = []
    for i, a in enumerate(actions):
        where = f"{label}[{i}]"
        if not isinstance(a, dict):
            errs.append(f"{where}: must be an object"); continue
        for k in ("action", "route", "reason"):
            if k not in a:
                errs.append(f"{where}: missing '{k}'")
        name = a.get("action")
        if name not in ALL_ACTIONS:
            errs.append(f"{where}: unknown action '{name}'"); continue
        names.append(name)
        if a.get("route") not in ROUTES:
            errs.append(f"{where}: route must be auto/L1/L2, got '{a.get('route')}'")
        elif a["route"] != route(name, exposure):
            errs.append(f"{where}: {name} with exposure ${exposure:.2f} must route "
                        f"'{route(name, exposure)}', got '{a['route']}'")
        if not str(a.get("reason", "")).strip():
            errs.append(f"{where}: reason is empty (cite the policy rule)")
    return names


def validate(ans, ref=None):
    errs, warns = [], []

    # ---- structure
    for k in TOP_KEYS:
        if k not in ans:
            errs.append(f"missing top-level field '{k}'")
    if errs:
        return errs, warns
    case, sar, nba = ans["case"], ans["sar"], ans["next_best_actions"]
    for k in CASE_KEYS:
        if k not in case: errs.append(f"case: missing '{k}'")
    for k in SAR_KEYS:
        if k not in sar: errs.append(f"sar: missing '{k}'")
    for k in ("initial", "final", "what_changed"):
        if k not in nba: errs.append(f"next_best_actions: missing '{k}'")
    if errs:
        return errs, warns

    if ref and ref.case_ids and ans["case_id"] not in ref.case_ids:
        errs.append(f"case_id '{ans['case_id']}' is not in case_pack.csv")

    # ---- case part
    if case["status"] not in STATUS: errs.append(f"case.status invalid: {case['status']}")
    if case["verdict"] not in VERDICT: errs.append(f"case.verdict invalid: {case['verdict']}")
    if case["pattern"] not in PATTERNS: errs.append(f"case.pattern invalid: {case['pattern']}")
    p = case["fraud_probability"]
    if not _is_num(p) or not 0 <= p <= 1:
        errs.append("case.fraud_probability must be a number between 0 and 1")
    exposure = case["exposure_usd"]
    if not _is_num(exposure) or exposure < 0:
        errs.append("case.exposure_usd must be a non-negative number"); exposure = 0.0

    for k in ("affected_txn_ids", "connected_card_ids", "connected_device_profiles",
              "similar_prior_cases"):
        v = case[k]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            errs.append(f"case.{k} must be a list of strings")
    if not isinstance(case["first_suspicious_txn_id"], str):
        errs.append("case.first_suspicious_txn_id must be a string (\"\" if none)")
    if not isinstance(case["summary"], str) or not case["summary"].strip():
        errs.append("case.summary is empty")

    if case["pattern"] == "undocumented" and not str(case["pattern_description"]).strip():
        errs.append("pattern 'undocumented' requires pattern_description")
    if case["pattern"] != "undocumented" and case["pattern_description"] != "":
        errs.append("pattern_description must be \"\" unless pattern is 'undocumented'")

    if case["written_to_graph"] and not case["graph_case_id"]:
        errs.append("written_to_graph is true but graph_case_id is empty")
    if not case["written_to_graph"] and case["graph_case_id"]:
        errs.append("graph_case_id is set but written_to_graph is false")

    aff = case["affected_txn_ids"] if isinstance(case["affected_txn_ids"], list) else []
    first = case["first_suspicious_txn_id"]
    if aff and first and first not in aff:
        errs.append("first_suspicious_txn_id must be one of affected_txn_ids")
    if aff and not first:
        warns.append("affected_txn_ids present but first_suspicious_txn_id is empty")
    if len(set(aff)) != len(aff):
        errs.append("affected_txn_ids contains duplicates (exposure would double count)")

    if case["verdict"] == "legitimate":
        if aff: errs.append("legitimate verdict: affected_txn_ids must be empty")
        if exposure != 0: errs.append("legitimate verdict: exposure_usd must be 0")
        if case["pattern"] != "none": warns.append("legitimate verdict but pattern is not 'none'")
    if case["verdict"] == "fraud" and not aff:
        errs.append("fraud verdict but affected_txn_ids is empty")
    if case["verdict"] == "fraud" and case["status"] == "closed_legitimate":
        errs.append("verdict fraud conflicts with status closed_legitimate")
    if case["verdict"] == "legitimate" and case["status"] == "closed_fraud":
        errs.append("verdict legitimate conflicts with status closed_fraud")

    # evidence
    ev = case["evidence"]
    if not isinstance(ev, list) or not ev:
        errs.append("case.evidence must be a non-empty list")
    else:
        for i, e in enumerate(ev):
            for k in ("claim", "source", "ref", "entity_ids"):
                if k not in e: errs.append(f"evidence[{i}]: missing '{k}'")
            if e.get("source") not in EVIDENCE_SOURCES:
                errs.append(f"evidence[{i}]: source must be one of {sorted(EVIDENCE_SOURCES)}")
            if not isinstance(e.get("entity_ids", []), list):
                errs.append(f"evidence[{i}]: entity_ids must be a list")

    # ---- dataset checks (only when a Reference is supplied)
    if ref:
        if ref.txn_amounts:
            for t in aff:
                if t not in ref.txn_amounts:
                    errs.append(f"affected txn '{t}' does not exist in the dataset")
            if first and first not in ref.txn_amounts:
                errs.append(f"first_suspicious_txn_id '{first}' does not exist in the dataset")
            known = [t for t in aff if t in ref.txn_amounts]
            if len(known) == len(aff) and aff:
                total = round(sum(abs(ref.txn_amounts[t]) for t in aff), 2)
                if abs(total - exposure) > 0.01:
                    errs.append(f"exposure_usd {exposure} != sum of affected amounts {total}")
        if ref.card_ids:
            for c in case["connected_card_ids"]:
                if c not in ref.card_ids: errs.append(f"connected card '{c}' not in dataset")
        if ref.closed_case_ids:
            for c in case["similar_prior_cases"]:
                if c not in ref.closed_case_ids: errs.append(f"similar_prior_case '{c}' not in closed cases")
    for c in case["connected_card_ids"]:
        if isinstance(c, str) and not CARD_RE.match(c):
            errs.append(f"connected card id looks malformed: '{c}' (expected like C12345-K1)")

    # ---- evidence requests
    reqs = ans["evidence_requests"]
    if not isinstance(reqs, list):
        errs.append("evidence_requests must be a list"); reqs = []
    for i, r in enumerate(reqs):
        if r.get("type") not in REQUEST_TYPES:
            errs.append(f"evidence_requests[{i}]: type must be one of {sorted(REQUEST_TYPES)}")
        if not isinstance(r.get("asked_after_step"), int) or isinstance(r.get("asked_after_step"), bool):
            errs.append(f"evidence_requests[{i}]: asked_after_step must be an integer")
        if not str(r.get("assumed_response", "")).strip():
            errs.append(f"evidence_requests[{i}]: assumed_response is empty")

    # ---- next best actions
    init = _actions(errs, nba["initial"], "next_best_actions.initial", exposure)
    fin = _actions(errs, nba["final"], "next_best_actions.final", exposure)
    if not init: errs.append("next_best_actions.initial is empty")
    if not fin: errs.append("next_best_actions.final is empty")
    if not reqs and nba["initial"] != nba["final"]:
        errs.append("no evidence requested, so final must equal initial")
    if reqs and nba["initial"] == nba["final"] and nba["what_changed"] != "nothing":
        warns.append("final equals initial but what_changed is not 'nothing'")
    if nba["initial"] != nba["final"] and str(nba["what_changed"]).strip().lower() in ("", "nothing"):
        errs.append("final differs from initial, so what_changed must explain why")
    if not reqs and nba["what_changed"] != "nothing":
        warns.append("no evidence requested; what_changed should be 'nothing'")

    # ---- policy consistency (uses final actions)
    if "FILE_REPORT" in fin and "CREATE_CASE" not in fin:
        errs.append("FILE_REPORT without CREATE_CASE (a report always has a case behind it)")
    if "BLOCK_ALL_CARDS" in fin:
        warns.append("BLOCK_ALL_CARDS needs R10: two confirmed-fraud cards or compromised credentials")
    if _is_num(p) and p >= CASE_MIN_PROB and "CREATE_CASE" not in fin and case["verdict"] != "legitimate":
        warns.append("probability >= 0.30 but no CREATE_CASE in final actions (policy 3a)")
    if reqs and "CREATE_CASE" not in init and "CREATE_CASE" not in fin:
        warns.append("evidence was requested but no CREATE_CASE (policy 3a)")
    if "BLOCK_CARD" in init and _is_num(p) and p < 0.70 and not reqs:
        warns.append("BLOCK_CARD recommended with p<0.70 and no verification (R1)")
    if case["verdict"] == "legitimate" and any(a in fin for a in ("BLOCK_CARD", "BLOCK_ALL_CARDS")):
        errs.append("legitimate verdict but a block action is recommended")
    if case["connected_card_ids"] and "MONITOR_CONNECTED_CARDS" not in fin and case["verdict"] == "fraud":
        warns.append("connected cards present but no MONITOR_CONNECTED_CARDS (R6)")

    # ---- SAR
    wants_report = "FILE_REPORT" in fin
    if bool(sar["file"]) != wants_report:
        errs.append("sar.file must agree with FILE_REPORT in final actions")
    if sar["file"]:
        n = sar["narrative"]
        if not isinstance(n, str) or not n.strip():
            errs.append("sar.file is true but narrative is empty")
        else:
            sentences = len([s for s in re.split(r"(?<=[.!?])\s+", n.strip()) if s])
            if not 6 <= sentences <= 12:
                warns.append(f"sar.narrative has {sentences} sentences (README asks for 6-12)")
        if not sar["subjects"]: errs.append("sar.subjects must list the IDs named in the narrative")
        d = sar["activity_dates"]
        if not (isinstance(d, list) and len(d) == 2 and all(isinstance(x, str) and DATE_RE.match(x) for x in d)):
            errs.append("sar.activity_dates must be two YYYY-MM-DD strings")
        elif d[0] > d[1]:
            errs.append("sar.activity_dates: first date is after last date")
        if not _is_num(sar["total_amount_usd"]) or abs(sar["total_amount_usd"] - exposure) > 0.01:
            errs.append("sar.total_amount_usd should equal case.exposure_usd")
        if case["verdict"] == "legitimate":
            errs.append("SAR filed for a legitimate verdict")
    else:
        if sar["narrative"] != "" or sar["subjects"] != [] or sar["activity_dates"] != [] \
                or sar["total_amount_usd"] != 0:
            errs.append("sar.file is false: narrative must be \"\", subjects [], total 0, dates []")
    if not str(sar["reason"]).strip():
        errs.append("sar.reason is empty (say why, cite the rule)")

    # ---- run stats
    if not str(ans["stop_reason"]).strip(): errs.append("stop_reason is empty")
    for k in ("tool_calls", "tokens"):
        if not isinstance(ans[k], int) or isinstance(ans[k], bool) or ans[k] < 0:
            errs.append(f"{k} must be a non-negative integer")
    if not _is_num(ans["latency_s"]) or ans["latency_s"] < 0:
        errs.append("latency_s must be a non-negative number")
    return errs, warns


def validate_dir(cases_dir="cases", case_pack_csv=None, ref=None):
    """Check every answer file; also confirms all 20 case_pack ids have a file."""
    report = {}
    files = {p.stem: p for p in Path(cases_dir).glob("*.json")}
    if case_pack_csv:
        import csv
        ids = [r["case_id"] for r in csv.DictReader(open(case_pack_csv, encoding="utf-8"))]
        for cid in ids:
            if cid not in files:
                report[cid] = (["answer file missing"], [])
    for cid, path in sorted(files.items()):
        try:
            ans = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            report[cid] = ([f"invalid JSON: {e}"], []); continue
        errs, warns = validate(ans, ref)
        if ans.get("case_id") != cid:
            errs.append(f"file name {cid}.json does not match case_id '{ans.get('case_id')}'")
        report[cid] = (errs, warns)
    return report


if __name__ == "__main__":
    import sys
    rep = validate_dir(sys.argv[1] if len(sys.argv) > 1 else "cases",
                       sys.argv[2] if len(sys.argv) > 2 else None)
    bad = 0
    for cid, (e, w) in rep.items():
        status = "OK " if not e else "FAIL"
        bad += bool(e)
        print(f"{status} {cid}  errors={len(e)} warnings={len(w)}")
        for m in e: print("   ERROR:", m)
        for m in w: print("   warn: ", m)
    print(f"\n{len(rep)-bad}/{len(rep)} files valid")
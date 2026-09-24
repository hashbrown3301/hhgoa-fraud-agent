"""SAR narrative builder: who, what, when, where, how, why - built ONLY from facts already
computed (assess.py's evidence + detectors.py's facts). The LLM (later) may reword this for
tone; it must not invent amounts, dates, ids or claims not present in `f`/`a`/`p`.
"""
import pandas as pd

REPORTABLE_PATTERNS = {
    "card_testing": "a card-testing sequence (small online authorizations followed by a larger purchase)",
    "card_not_present_fraud": "unauthorized card-not-present activity",
    "card_not_present_new_device": "unauthorized card-not-present activity from a device not previously seen on this account",
    "out_of_region_use": "unauthorized use in a billing region with no prior history on this card",
    "account_takeover": "activity inconsistent with the cardholder's established pattern, consistent with account takeover",
    "undocumented": "a coordinated pattern not matching any documented fraud typology",
}


def _dt(ts):
    return pd.Timestamp(ts)


def narrative(case_id, customer_id, card_id, f, a, p):
    """6-12 sentences, each stating one fact. No invented details."""
    ep_ids = a["episode_txn_ids"]
    dates = sorted({_dt(f["episode"]["start"]).date(), _dt(f["episode"]["end"]).date()})
    date_str = str(dates[0]) if len(dates) == 1 else f"{dates[0]} to {dates[-1]}"
    exp = a["exposure_usd"]
    n = len(ep_ids)
    pat_desc = REPORTABLE_PATTERNS.get(a["pattern"], "suspicious activity")

    s = []
    s.append(f"This report concerns card {card_id} held by customer {customer_id}, investigated as case {case_id}.")
    s.append(f"{n} transaction{'s' if n != 1 else ''} on {date_str} totalling ${exp:,.2f} "
             f"{'were' if n != 1 else 'was'} identified as {pat_desc}.")

    # WHAT / HOW - lead with the strongest evidence
    for key in ("sequence", "cross_card_link", "device_anomaly", "baseline_deviation"):
        ev = a["evidence_for"].get(key)
        if ev:
            s.append(ev["claim"].rstrip(".") + ".")
    if a.get("customer_denial"):
        s.append("The cardholder was contacted and denied making these transactions.")

    # connected activity
    conn = p.get("connected") or {}
    if conn.get("customers"):
        s.append(f"The same device profile was also used on {len(conn['customers'])} other customer accounts "
                 f"in the surrounding window, {len(conn.get('cards', []))} of which are identified in our records.")
    if a.get("precedent"):
        s.append(f"This device model also appears in {len(a['precedent']['cases'])} prior confirmed-fraud "
                 f"cases: {', '.join(a['precedent']['cases'][:4])}.")

    # WHY / assessment basis
    s.append(f"The investigation assessed the fraud probability at {a['probability']:.2f} "
             f"based on {len(a['evidence_for'])} independent piece(s) of corroborating evidence, "
             f"following {a['rule']}.")

    # actions taken
    acts = [x["action"].replace("_", " ").title() for x in p["final"]]
    s.append(f"Actions taken or recommended: {', '.join(acts)}.")

    return " ".join(s)


def build_sar(case_id, customer_id, card_id, f, a, p, link, undoc):
    """Returns the schema-shaped `sar` dict. `link`/`undoc` are the same booleans actions.py
    used to decide FILE_REPORT, so the reason here always matches why the action was taken."""
    from .policy import REPORT_MIN_EXPOSURE
    fin_names = {x["action"] for x in p["final"]}
    file_it = "FILE_REPORT" in fin_names
    if not file_it:
        from .schema import no_sar
        why = ("verdict is not confirmed/strongly-suspected fraud" if a["verdict"] != "fraud" else
               "exposure and links do not meet the reporting trigger (3a)")
        return no_sar(f"No SAR required: {why}.")

    exp = a["exposure_usd"]
    reasons = []
    if exp > REPORT_MIN_EXPOSURE:
        reasons.append(f"exposure ${exp:,.2f} exceeds the $1,000 threshold")
    if link:
        reasons.append("connected to other cards via a shared device profile (R6)")
    if undoc:
        reasons.append("undocumented coordinated pattern (R9)")
    dates = sorted({str(pd.Timestamp(f["episode"]["start"]).date()), str(pd.Timestamp(f["episode"]["end"]).date())})
    if len(dates) == 1:
        dates = dates * 2
    return {
        "file": True,
        "reason": "3a: " + "; ".join(reasons),
        "narrative": narrative(case_id, customer_id, card_id, f, a, p),
        "subjects": [customer_id],
        "total_amount_usd": round(exp, 2),
        "activity_dates": dates,
    }
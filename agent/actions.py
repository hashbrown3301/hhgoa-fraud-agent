"""Turn an assessment into policy-compliant next best actions (initial and final).

Every action name, route and rule citation comes from policy.py / the README policy.
The customer's answer is SIMULATED (deterministic rule below) and is always recorded in
evidence_requests so the assumption is visible.
"""
from .assess import assess
from .policy import should_file_report, ESCALATE_EXPOSURE, REPORT_MIN_EXPOSURE
from .schema import action, evidence_request

ASKED_AFTER_STEP = 5      # steps done before asking: txn, baseline/region, episode/device, cross-card/memory, assess


def simulate_reply(a0):
    """Deterministic stand-in for the customer/step-up answer: assume what the evidence leans toward."""
    p = a0["probability"]
    if p >= 0.50:
        return "denies", (f"Assumed the cardholder denies the activity (evidence leans fraud, p={p:.2f}). "
                          f"SIMULATED: no real reply is available in this exercise.")
    return "confirms", (f"Assumed the cardholder confirms the activity (evidence leans legitimate, p={p:.2f}). "
                        f"SIMULATED: no real reply is available in this exercise.")


def _shared_link(a):
    return "cross_card_link" in a["evidence_for"]


def _r7(a, trigger):
    """Disputed but legitimate: a denial that matches the card's own recurring pattern."""
    ag = a["evidence_against"]
    return (trigger == "customer_report" and not a["evidence_for"] and
            len(ag) >= 3 and "recurring_amount" in ag)


def initial_actions(a, f, trigger):
    exp, p = a["exposure_usd"], a["probability"]
    acts = []
    if a["verdict"] == "legitimate":
        acts.append(action("ALLOW_TRANSACTION", f"R1: no signal to justify a block; p={p:.2f}, routine activity", exp))
        acts.append(action("CLOSE_NO_FRAUD", f"Stop rule: p<=0.15 with {len(a['evidence_against'])} independent routine-match facts", exp))
        return acts
    if a["verdict"] == "uncertain":
        if _r7(a, trigger):
            return [action("CREATE_CASE", "R7: disputed charge matches the card's own recurring pattern; case opened on dispute (3a)", exp),
                    action("VERIFY_WITH_CUSTOMER", "R7: ask whether this is the recurring charge; do not block", exp),
                    action("WARN_CUSTOMER", "R7: send a recurring-charge reminder", exp)]
        req = "STEP_UP_AUTH" if a["evidence_request"] == "step_up_auth" else "VERIFY_WITH_CUSTOMER"
        acts.append(action(req, f"R1: p={p:.2f} rests on weak or conflicting signals; verify before any block", exp))
        acts.append(action("CREATE_CASE", "3a: evidence requested and p>=0.30", exp))
        if exp > ESCALATE_EXPOSURE:
            acts.append(action("ESCALATE_TO_ANALYST", f"R8: verdict uncertain and exposure ${exp:,.2f} exceeds $500", exp))
        return acts
    return _fraud_actions(a, f, trigger, denied=a["customer_denial"])


def _fraud_actions(a, f, trigger, denied):
    exp, p = a["exposure_usd"], a["probability"]
    link, undoc, testing = _shared_link(a), a["pattern"] == "undocumented", a["pattern"] == "card_testing"
    acts = []
    if testing:
        acts.append(action("DECLINE_TRANSACTION", "R5: testing sequence observed", exp))
        acts.append(action("STEP_UP_AUTH", "R5: require step-up before further activity", exp))
        if f["card_testing"]["followup_max_amt"] > 100:
            acts.append(action("BLOCK_CARD", f"R5: a purchase over $100 already cleared; exposure ${exp:,.2f}", exp))
    else:
        why = "R2: customer denied the activity" if denied else \
              f"p={p:.2f} with {len(a['evidence_for'])} independent signals (not a single-signal case, R1 does not apply)"
        acts.append(action("BLOCK_CARD", f"{why}; exposure ${exp:,.2f}", exp))
    acts.append(action("CREATE_CASE", "R2/R6/R9: fraud case with evidence attached" if (denied or link or undoc) else "3a: p>=0.30", exp))
    if should_file_report(p, exp, link, undoc):
        reasons = []
        if exp > REPORT_MIN_EXPOSURE: reasons.append(f"exposure ${exp:,.2f} exceeds $1,000")
        if link: reasons.append("connected to a shared device profile / other cards (R6)")
        if undoc: reasons.append("undocumented coordinated pattern (R9)")
        acts.append(action("FILE_REPORT", "3a" + (" and R2" if denied else "") + ": " + "; ".join(reasons), exp))
    if link:
        acts.append(action("MONITOR_CONNECTED_CARDS", "R6: other cards share this device profile", exp))
    if undoc:
        acts.append(action("ESCALATE_TO_ANALYST", "R9: describe the undocumented pattern for an analyst", exp))
    return acts


def final_actions(a0, a1, f, trigger, reply):
    """Actions after the simulated reply (or the initial ones if nothing was requested)."""
    exp = a1["exposure_usd"]
    if reply == "confirms":
        acts = []
        if a0["verdict"] == "uncertain":
            acts.append(action("CREATE_CASE", "3a: case opened when evidence was requested; closed as legitimate", exp))
        acts.append(action("CLOSE_NO_FRAUD", "R3: customer confirmed the transaction; confirmation noted in the case", exp))
        if _r7(a0, trigger):
            acts.append(action("WARN_CUSTOMER", "R7: recurring-charge reminder", exp))
        return acts
    if a1["verdict"] == "fraud":
        return _fraud_actions(a1, f, trigger, denied=True)
    # Customer denies, but the denial alone doesn't clear the fraud threshold (no corroborating
    # evidence, p still < 0.70): don't loop back to another verification request, and don't block
    # on an unresolved single signal (R1) - hand it to a human instead (R8).
    return [action("CREATE_CASE", "R2: customer denies the activity, but no corroborating evidence strengthens the case", exp),
            action("ESCALATE_TO_ANALYST", f"R8: verdict remains uncertain (p={a1['probability']:.2f}) after verification; needs human judgement", exp)]


def connected(f, card_lookup=None):
    """Other cards on the same device profile (only ids that exist in the dataset files)."""
    sd = f.get("shared_device") or {}
    if not sd.get("ring_like"):
        return {"customers": [], "cards": [], "profiles": []}
    custs = [c["customer_id"] for c in sd["other_customers"] if c["n_marked_new"] > 0]
    cards = []
    for c in custs:
        cards += (card_lookup or {}).get(c, [])
    return {"customers": custs, "cards": sorted(set(cards)), "profiles": [sd["profile"]]}


def plan_case(f, trigger_type, memory=None, as_of=None, card_lookup=None):
    """Full two-stage plan: assess, maybe ask, re-assess, recommend before and after."""
    a0 = assess(f, trigger_type, memory, as_of)
    initial = initial_actions(a0, f, trigger_type)
    out = {"a0": a0, "a1": a0, "reply": None, "evidence_requests": [], "initial": initial,
           "final": initial, "what_changed": "nothing", "connected": connected(f, card_lookup)}
    if a0["evidence_request"]:
        reply, assumption = simulate_reply(a0)
        a1 = assess(f, trigger_type, memory, as_of, reply=reply)
        final = final_actions(a0, a1, f, trigger_type, reply)
        kind = "step_up_auth" if a0["evidence_request"] == "step_up_auth" else "customer_validation"
        out.update(a1=a1, reply=reply, final=final,
                   evidence_requests=[evidence_request(kind, ASKED_AFTER_STEP, assumption)],
                   what_changed=(f"Simulated reply ({reply}) moved probability from {a0['probability']:.2f} to "
                                 f"{a1['probability']:.2f}; actions changed from {[x['action'] for x in initial]} to "
                                 f"{[x['action'] for x in final]}."))
    return out
"""Turn detector facts into a verdict, pattern and probability band.

No fitted weights. A decision table over INDEPENDENT kinds of evidence, mirroring the
policy's own logic (R1, section 6): strong evidence = an event sequence or a link to other
cards; weak evidence = a deviation from the card's baseline or a device anomaly; the customer's
denial is its own kind. Routine-match facts count against. The LLM later explains and may
adjust inside the band, but the band, verdict and stop decision are decided here.
"""
import re
from .policy import can_stop

VERDICT_FRAUD, VERDICT_UNCERTAIN = 0.70, 0.30         # p >= 0.70 fraud, p < 0.30 legitimate
RARE_TOKEN_MAX = 30                                    # a device token in <=30 closed cases is 'rare'
AGGREGATE_PROFILE_MIN = 25                             # this many distinct device profiles on one
                                                        # card_id means it likely bundles many real
                                                        # cardholders; "nothing deviates" is then weak
                                                        # evidence of innocence, backed by backtesting
                                                        # this rule against the closed-case history


def _flags(f):
    out = set(f["flagged"]["flags"])
    for fl in f["episode"]["flags_by_txn"].values():
        out |= set(fl)
    return out


def device_token(profile):
    """Device model at the start of a profile, e.g. 'SM-G935F' (None if too generic)."""
    m = re.match(r"^([A-Za-z0-9\-_/\.]+)", (profile or "").split(" | ")[0])
    return m.group(1) if m else None


def precedent(f, memory, as_of):
    """Closed confirmed cases sharing a RARE device token with this alert."""
    tok = device_token(f["device"]["profile"])
    if not tok or memory is None:
        return None
    hits = memory.token_cases(tok, as_of=as_of)
    fraud = [h for h in hits if h["outcome"] == "confirmed_fraud"]
    if 2 <= len(hits) <= RARE_TOKEN_MAX and len(fraud) >= 2:
        return {"token": tok, "cases": [h["case_id"] for h in fraud],
                "patterns": sorted({h["pattern"] for h in fraud})}
    return None


def evidence_types(f, memory=None, as_of=None):
    """Which independent kinds of evidence are present, each with a plain-language claim."""
    fl, flags, reg, dev, ep = f["flagged"], _flags(f), f["region"], f["device"], f["episode"]
    base = f["baseline"]
    found = {}
    # A: deviation from this card's own baseline (weak)
    dev_flags = sorted(flags & {"new_region", "new_product", "amount_outlier", "rare_channel"})
    region_unseen = reg["prior_visits"] == 0 and reg["region"] is not None and base["n"] >= 20
    if dev_flags or region_unseen:
        bits = list(dev_flags) + (["billing_region_never_seen"] if region_unseen else [])
        found["baseline_deviation"] = {"strength": "weak", "detail": bits,
            "claim": "Deviates from this card's baseline: " + ", ".join(bits).replace("_", " "),
            "entity_ids": ep["txn_ids"]}
    # B: device / identity anomaly (weak: people buy new phones)
    if dev["marked_new"] or dev["proxy"] or flags & {"new_device", "proxy"}:
        bits = (["device marked New"] if dev["marked_new"] or "new_device" in flags else []) + \
               ([f"proxy {dev['proxy']}"] if dev["proxy"] else [])
        found["device_anomaly"] = {"strength": "weak", "detail": bits,
            "claim": "Identity record: " + ", ".join(bits), "entity_ids": ep["txn_ids"]}
    # C: an event sequence (strong)
    if f["card_testing"]["detected"] or ep["deviating_txns"] >= 2:
        n = ep["deviating_txns"]
        claim = ("Testing sequence: >=3 tiny online authorizations then a larger purchase"
                 if f["card_testing"]["detected"] else
                 f"{n} deviating transactions within {ep['start'][:16]} to {ep['end'][:16]} totalling ${ep['exposure_usd']:,.2f}")
        found["sequence"] = {"strength": "strong", "detail": [claim], "claim": claim, "entity_ids": ep["txn_ids"]}
    # D: link to other cards (strong)
    sd = f.get("shared_device") or {}
    pre = precedent(f, memory, as_of)
    if sd.get("ring_like") or pre:
        st = sd.get("stats") or {}
        parts = []
        if sd.get("ring_like"):
            parts.append(f"device profile used by {st['n_customers']} cards, {st['new_rate']:.0%} marked New, "
                         f"mean risk score only {st['mean_risk_score']}")
        if pre:
            parts.append(f"device model {pre['token']} appears in closed confirmed cases {', '.join(pre['cases'][:4])}")
        found["cross_card_link"] = {"strength": "strong", "detail": parts, "claim": "; ".join(parts),
            "entity_ids": [c["customer_id"] for c in (sd.get("other_customers") or [])[:10]] + (pre["cases"] if pre else [])}
    return found, pre


def counter_evidence(f):
    """Facts that look like the cardholder's normal behaviour."""
    fl, reg, dev, base, rec = f["flagged"], f["region"], f["device"], f["baseline"], f["amount_recurrence"]
    c = {}
    if reg["routine"]:
        c["routine_region"] = f"billing region {reg['region']} visited {reg['prior_visits']} times over {reg['distinct_weeks']} weeks"
    if base["n"] >= 20 and fl["amount"] <= base["amt_p95"]:
        c["typical_amount"] = f"${fl['amount']:.2f} is within this card's 95th percentile (${base['amt_p95']:.2f})"
    if fl["channel"] == "online" and base["online_share"] >= 0.30:
        c["typical_channel"] = f"card is online {base['online_share']:.0%} of the time"
    if fl["channel"] == "in_person" and base["online_share"] < 0.50:
        c["typical_channel"] = f"card is in-person {1 - base['online_share']:.0%} of the time"
    if dev["profile_seen_before"] and not dev["marked_new"]:
        c["known_device"] = "device profile already seen on this card"
    if rec.get("regular"):
        c["recurring_amount"] = (f"{rec['similar_amount_prior']} earlier transactions of a similar amount, "
                                 f"roughly every {rec['gap_days_mean']:.0f} days (regular cadence)")
    return c


def band(strong, weak, denial, counters, aggregate=False):
    """The decision table. Returns (probability, rule text).
    `aggregate` = this card shows heavy device-profile diversity (see AGGREGATE_PROFILE_MIN):
    it likely bundles many real cardholders, so a card with NO deviation still isn't
    trustworthy evidence of one specific person's innocence (see the HHG-007 writeup)."""
    s, w, n_c = len(strong), len(weak), len(counters)
    if denial:
        if s + w >= 1:
            return 0.90, "customer denial plus at least one independent anomaly (R2)"
        if n_c >= 3:
            return 0.45, "customer denies, but activity matches the card's routine: evidence conflicts (R7/R8)"
        return 0.60, "customer denial with no supporting anomaly"
    if s >= 1 and s + w >= 2:
        return 0.88, "a strong signal plus at least one more independent signal"
    if s == 1:
        return 0.65, "a single strong signal, nothing corroborating"
    if w >= 2:
        return (0.60 if n_c <= 1 else 0.50), "two weak signals; people do buy new phones (R1: verify)"
    if w == 1:
        return (0.45 if n_c <= 1 else 0.30), "a single weak signal (R1: verify before any block)"
    if aggregate:
        return 0.25, ("no deviation found, but this card shows heavy device-profile diversity "
                      f"(>= {AGGREGATE_PROFILE_MIN} distinct profiles): it likely bundles many real "
                      "cardholders, so a routine match alone is not reliable evidence here (R1: verify)")
    return (0.08 if n_c >= 2 else 0.20), "no deviation from the card's behaviour"


def pick_pattern(f, found, p):
    """Map evidence to the README's pattern names (or none)."""
    if p < VERDICT_UNCERTAIN or not found:      # nothing but a denial or a score: no pattern to name
        return "none", ""
    fl, dev = f["flagged"], f["device"]
    if f["card_testing"]["detected"]:
        return "card_testing", ""
    cross = found.get("cross_card_link")
    if cross and f.get("shared_device", {}).get("ring_like"):
        return "undocumented", ("Many cards show purchases from one device profile that is marked New every time, behind an "
                                "anonymous proxy, with low model scores. " + cross["claim"] + ". Matches no documented typology.")
    if fl["channel"] == "online":
        return ("card_not_present_new_device" if "device_anomaly" in found else "card_not_present_fraud"), ""
    if "baseline_deviation" in found and any("region" in d for d in found["baseline_deviation"]["detail"]):
        return "out_of_region_use", ""
    return "account_takeover", ""


def assess(f, trigger_type, memory=None, as_of=None, reply=None):
    """reply: None | 'denies' | 'confirms'  (simulated customer answer, recorded by the caller)."""
    found, pre = evidence_types(f, memory, as_of)
    counters = counter_evidence(f)
    strong = [k for k, v in found.items() if v["strength"] == "strong"]
    weak = [k for k, v in found.items() if v["strength"] == "weak"]
    denial = trigger_type == "customer_report" or reply == "denies"
    aggregate = len(f.get("baseline", {}).get("profiles") or []) >= AGGREGATE_PROFILE_MIN
    if reply == "confirms":
        p, rule = 0.03, "customer confirmed the transaction (R3)"
        denial = False
    else:
        p, rule = band(strong, weak, denial, counters, aggregate=aggregate)
    verdict = "fraud" if p >= VERDICT_FRAUD else "uncertain" if p >= VERDICT_UNCERTAIN else "legitimate"
    pattern, pdesc = pick_pattern(f, found, p)
    n_indep = (len(found) + int(denial)) if p >= 0.5 else len(counters)
    stop, why = can_stop(p, n_indep, verification_settled=reply is not None, no_further_value=False)
    request = None
    if verdict == "uncertain" and not stop:
        request = "step_up_auth" if ("device_anomaly" in found and f["flagged"]["channel"] == "online") else "customer_validation"
    return {"probability": p, "verdict": verdict, "rule": rule, "pattern": pattern, "pattern_description": pdesc,
            "evidence_for": found, "evidence_against": counters, "customer_denial": denial,
            "aggregate_account": aggregate, "stop": stop, "stop_reason": why, "evidence_request": request,
            "precedent": pre, "exposure_usd": f["episode"]["exposure_usd"],
            "episode_txn_ids": f["episode"]["txn_ids"], "first_txn_id": f["episode"]["first_txn_id"],
            "nearby_other_suspicious": f["episode"]["nearby_other_suspicious"]}
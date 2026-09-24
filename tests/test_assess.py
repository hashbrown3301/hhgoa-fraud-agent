import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.assess import band, assess


def facts(**kw):
    f = {"flagged": {"txn": "1", "channel": "online", "amount": 50.0, "flags": [], "risk_score": 0.5, "region": "300.0"},
         "baseline": {"n": 100, "amt_p95": 100.0, "online_share": 0.5},
         "region": {"prior_visits": 20, "routine": True, "region": "300.0", "distinct_weeks": 10},
         "amount_recurrence": {"share_of_history_with_similar_amount": 0.1, "similar_amount_prior": 10, "similar_amount_same_region": 5},
         "card_testing": {"detected": False}, "device": {"profile": "", "marked_new": False, "proxy": None, "profile_seen_before": False},
         "episode": {"txn_ids": ["1"], "first_txn_id": "1", "exposure_usd": 50.0, "deviating_txns": 0, "flags_by_txn": {"1": []},
                     "start": "2016-12-01 10:00:00", "end": "2016-12-01 10:00:00", "nearby_other_suspicious": []},
         "shared_device": {"ring_like": False}}
    for k, v in kw.items():
        f[k] = v
    return f


def test_routine_is_legitimate_and_stops():
    a = assess(facts(), "risk_score")
    assert a["verdict"] == "legitimate" and a["stop"] and a["probability"] <= 0.15


def test_one_weak_signal_asks_for_evidence():
    f = facts(device={"profile": "x", "marked_new": True, "proxy": None, "profile_seen_before": False})
    f["flagged"]["flags"] = ["new_device"]
    a = assess(f, "risk_score")
    assert a["verdict"] == "uncertain" and not a["stop"] and a["evidence_request"] == "step_up_auth"


def test_two_weak_signals_not_enough_to_stop():
    p, _ = band([], ["baseline_deviation", "device_anomaly"], False, {})
    assert 0.30 <= p < 0.70


def test_strong_plus_weak_is_fraud():
    p, _ = band(["sequence"], ["device_anomaly"], False, {"a": 1, "b": 2})
    assert p >= 0.85


def test_denial_conflicting_with_routine_is_uncertain():
    a = assess(facts(), "customer_report")
    assert a["verdict"] == "uncertain"


def test_reply_changes_outcome():
    f = facts(); f["flagged"]["flags"] = ["amount_outlier"]
    first = assess(f, "risk_score")
    denied = assess(f, "risk_score", reply="denies")
    confirmed = assess(f, "risk_score", reply="confirms")
    assert first["verdict"] == "uncertain" and denied["verdict"] == "fraud" and confirmed["verdict"] == "legitimate"
    assert denied["stop"] and confirmed["stop"]


def test_denial_without_anomaly_names_no_pattern():
    a = assess(facts(), "customer_report")
    assert a["pattern"] == "none"
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agent.actions import plan_case


def facts(**kw):
    f = {"flagged": {"txn": "1", "channel": "online", "amount": 50.0, "flags": [], "risk_score": 0.5, "region": "300.0"},
         "baseline": {"n": 100, "amt_p95": 100.0, "online_share": 0.5},
         "region": {"prior_visits": 20, "routine": True, "region": "300.0", "distinct_weeks": 10},
         "amount_recurrence": {"share_of_history_with_similar_amount": 0.1, "similar_amount_prior": 10, "similar_amount_same_region": 5},
         "card_testing": {"detected": False, "followup_max_amt": 0.0},
         "device": {"profile": "", "marked_new": False, "proxy": None, "profile_seen_before": False},
         "episode": {"txn_ids": ["1"], "first_txn_id": "1", "exposure_usd": 50.0, "deviating_txns": 0, "flags_by_txn": {"1": []},
                     "start": "2016-12-01 10:00:00", "end": "2016-12-01 10:00:00", "nearby_other_suspicious": []},
         "shared_device": {"ring_like": False}}
    for k, v in kw.items():
        f[k] = v
    return f


def names(acts): return [a["action"] for a in acts]


def weak_online():
    f = facts(device={"profile": "x", "marked_new": True, "proxy": None, "profile_seen_before": False})
    f["flagged"]["flags"] = ["new_device"]; f["baseline"]["online_share"] = 0.1
    return f


def test_legit_allows_and_closes():
    p = plan_case(facts(), "risk_score")
    assert names(p["initial"]) == ["ALLOW_TRANSACTION", "CLOSE_NO_FRAUD"] and p["final"] == p["initial"]
    assert p["evidence_requests"] == [] and p["what_changed"] == "nothing"


def test_uncertain_verifies_first_never_blocks():
    p = plan_case(weak_online(), "risk_score")
    assert "BLOCK_CARD" not in names(p["initial"]) and names(p["initial"])[0] in ("STEP_UP_AUTH", "VERIFY_WITH_CUSTOMER")
    assert "CREATE_CASE" in names(p["initial"]) and len(p["evidence_requests"]) == 1


def test_low_p_reply_confirms_and_closes():
    p = plan_case(weak_online(), "risk_score")          # p leans legitimate -> simulated confirm (R3)
    assert p["reply"] == "confirms" and "CLOSE_NO_FRAUD" in names(p["final"]) and "BLOCK_CARD" not in names(p["final"])


def test_denial_blocks_and_reports_over_1000():
    f = weak_online(); f["episode"]["exposure_usd"] = 1500.0; f["flagged"]["amount"] = 1500.0
    f["baseline"]["amt_p95"] = 100.0
    f["flagged"]["flags"] = ["new_device", "amount_outlier"]
    p = plan_case(f, "customer_report")
    fin = {a["action"]: a["route"] for a in p["final"]}
    assert fin["BLOCK_CARD"] == "L1" and fin["CREATE_CASE"] == "auto" and fin["FILE_REPORT"] == "L2"


def test_block_over_2500_is_L2():
    f = weak_online(); f["episode"]["exposure_usd"] = 3000.0
    f["flagged"]["flags"] = ["new_device", "amount_outlier"]
    fin = {a["action"]: a["route"] for a in plan_case(f, "customer_report")["final"]}
    assert fin["BLOCK_CARD"] == "L2"
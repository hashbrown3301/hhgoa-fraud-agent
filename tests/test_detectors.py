import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from agent.detectors import *


def frame(rows):
    df = pd.DataFrame(rows, columns=["ts", "channel", "TransactionAmt", "ProductCD", "addr1", "id_15"])
    df["ts"] = pd.to_datetime(df["ts"])
    df["customer_id"] = "C00001"; df["risk_score"] = 0.1; df["id_23"] = None
    df["DeviceType"] = None; df["DeviceInfo"] = None
    for c in ("id_30", "id_31", "id_33", "R_emaildomain"):
        df[c] = None
    df["TransactionID"] = range(1, len(df) + 1); df["txn"] = df["TransactionID"].astype(str)
    df = add_profile(df)
    return df.sort_values("ts").reset_index(drop=True)


def routine_rows(n=40):
    base = pd.Timestamp("2016-09-01 18:00")
    return [(base + pd.Timedelta(days=3 * i), "in_person", 50.0, "W", 300.0, None) for i in range(n)]


def test_card_testing_detected():
    rows = routine_rows() + [("2016-12-31 02:00", "online", 1.2, "C", 300.0, "New"),
                             ("2016-12-31 02:10", "online", 2.4, "C", 300.0, "New"),
                             ("2016-12-31 02:20", "online", 0.9, "C", 300.0, "New"),
                             ("2016-12-31 02:50", "online", 259.0, "C", 300.0, "New")]
    h = frame(rows); row = h.iloc[-1]
    ct = card_testing(h, row)
    assert ct["detected"] and len(ct["tiny_ids"]) == 3 and len(ct["followup_ids"]) == 1
    ep = find_episode(h, row)
    assert len(ep["txn_ids"]) == 4 and abs(ep["exposure_usd"] - 263.5) < 0.01


def test_normal_routine_is_alone_and_routine():
    h = frame(routine_rows())
    row = h.iloc[-1]
    assert not card_testing(h, row)["detected"]
    assert find_episode(h, row)["txn_ids"] == [row["txn"]]
    assert region_stats(h, row)["routine"]


def test_no_chain_through_unflagged_txn():
    rows = routine_rows() + [("2016-12-31 10:00", "in_person", 50.0, "W", 300.0, None)]
    h = frame(rows)
    assert len(find_episode(h, h.iloc[-1])["txn_ids"]) == 1


def test_as_of_hides_the_future():
    h = frame(routine_rows() + [("2017-01-05 10:00", "in_person", 50.0, "W", 300.0, None)])
    assert len(visible(h, "2016-12-31")) == len(h) - 1


def test_new_region_flag():
    rows = routine_rows() + [("2016-12-31 12:00", "in_person", 60.0, "W", 999.0, None)]
    h = frame(rows); row = h.iloc[-1]
    assert "new_region" in find_episode(h, row)["flags_by_txn"][row["txn"]]
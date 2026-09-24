"""Behaviour features for one transaction, computed only from what was known before it.
Used to (a) describe closed cases the same way as new alerts and (b) train a calibrated
fraud-probability model on the bank's labelled history."""
import numpy as np
import pandas as pd
from .detectors import baseline, region_stats, txn_flags, find_episode, EPISODE_HOURS

FEATURES = ["online", "log_region_visits", "region_routine", "new_region", "log_amt_over_median",
            "log_amt_over_p95", "new_product", "new_device", "profile_seen_before", "proxy",
            "rare_channel", "baseline_online_share", "log_history_n", "episode_len",
            "log_episode_usd", "risk_score", "tiny_online", "amount_outlier",
            "same_region_txns_72h", "other_region_txns_24h"]


def txn_features(h, row):
    """h = this card's history (any length); only rows strictly before row.ts are used as baseline."""
    h = h[h["ts"] <= row["ts"]]
    base = baseline(h, row["ts"] - pd.Timedelta(hours=EPISODE_HOURS))
    flags = set(txn_flags(row, base, h))
    reg = region_stats(h, row)
    ep = find_episode(h, row)
    prior = h[h["ts"] < row["ts"] - pd.Timedelta(hours=EPISODE_HOURS)]
    prof = row.get("profile", "") or ""
    amt = float(row["TransactionAmt"])
    d72 = h[(h["ts"] < row["ts"]) & (h["ts"] >= row["ts"] - pd.Timedelta(hours=72))]
    d24 = d72[d72["ts"] >= row["ts"] - pd.Timedelta(hours=24)]
    same_reg = int((d72["addr1"] == row["addr1"]).sum()) if pd.notna(row["addr1"]) else 0
    other_reg = int(((d24["addr1"] != row["addr1"]) & (d24["channel"] == "in_person")).sum())
    return {
        "same_region_txns_72h": same_reg,        # several days in one region = a trip, not a clone
        "other_region_txns_24h": other_reg,      # home activity continuing = a clone, not a trip
        "online": int(row["channel"] == "online"),
        "log_region_visits": float(np.log1p(reg["prior_visits"])),
        "region_routine": int(reg["routine"]),
        "new_region": int("new_region" in flags),
        "log_amt_over_median": float(np.log((amt + 1) / (base["amt_median"] + 1))),
        "log_amt_over_p95": float(np.log((amt + 1) / (base["amt_p95"] + 1))),
        "new_product": int("new_product" in flags),
        "new_device": int(row.get("id_15") == "New"),
        "profile_seen_before": int(bool(prof) and bool((prior["profile"] == prof).any())),
        "proxy": int(pd.notna(row.get("id_23"))),
        "rare_channel": int("rare_channel" in flags),
        "baseline_online_share": base["online_share"],
        "log_history_n": float(np.log1p(base["n"])),
        "episode_len": len(ep["txn_ids"]),
        "log_episode_usd": float(np.log1p(ep["exposure_usd"])),
        "risk_score": float(row["risk_score"]),
        "tiny_online": int("tiny_online" in flags),
        "amount_outlier": int("amount_outlier" in flags),
    }


def closed_case_txn(case):
    """The transaction a closed case is 'about': first fraud txn, or the cleared alert's txn."""
    if pd.notna(case["first_fraud_txn_id"]):
        return str(int(case["first_fraud_txn_id"]))
    ids = str(case["txn_ids"]).split("|")
    return ids[0] if ids and ids[0] not in ("", "nan") else None


def build_closed_features(tx, closed):
    """tx = transactions frame from load_transactions (must include the closed cases' customers)."""
    rows = []
    by_cust = {c: g.reset_index(drop=True) for c, g in tx.groupby("customer_id")}
    for _, c in closed.iterrows():
        t = closed_case_txn(c)
        h = by_cust.get(c["customer_id"])
        if t is None or h is None:
            continue
        m = h[h["txn"] == t]
        if m.empty:
            continue
        f = txn_features(h, m.iloc[0])
        f.update(case_id=c["case_id"], customer_id=c["customer_id"], txn=t,
                 pattern=c["pattern"], fraud=int(c["outcome"] == "confirmed_fraud"))
        rows.append(f)
    return pd.DataFrame(rows)
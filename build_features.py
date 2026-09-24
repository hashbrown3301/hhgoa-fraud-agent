"""Compute behaviour features for every closed case (run once, from the hhgoa folder)."""
import pandas as pd
from agent.detectors import add_profile
from agent.features import build_closed_features
from agent.model import evaluate

closed = pd.read_csv("data/closed_cases_history.csv")
cust = set(closed["customer_id"])
cols = ["TransactionID", "customer_id", "ts", "channel", "risk_score", "TransactionAmt",
        "ProductCD", "addr1", "addr2", "dist1"]

parts = []
for chunk in pd.read_csv("data/transactions.csv", usecols=cols, chunksize=200_000):
    parts.append(chunk[chunk["customer_id"].isin(cust)])
tx = pd.concat(parts, ignore_index=True)

ident = pd.read_csv("data/identity.csv",
                    usecols=["TransactionID", "DeviceType", "DeviceInfo", "id_15", "id_23", "id_30", "id_31", "id_33"])
tx = tx.merge(ident, on="TransactionID", how="left")
tx["ts"] = pd.to_datetime(tx["ts"])
tx["txn"] = tx["TransactionID"].astype(str)
tx = add_profile(tx).sort_values(["customer_id", "ts"]).reset_index(drop=True)
print("transactions loaded:", len(tx), "| customers:", tx["customer_id"].nunique())

F = build_closed_features(tx, closed)
F.to_csv("data/closed_features.csv", index=False)
print("cases featurized:", len(F), "of", len(closed))
print(F.groupby("fraud").size().to_dict())
print(evaluate(F))
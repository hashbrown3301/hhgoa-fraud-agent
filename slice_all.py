import pandas as pd

cases = pd.read_csv("data/case_pack.csv")
customers = set(cases["customer_id"])                      # all 20 cases

ident = pd.read_csv("data/identity.csv")
ident_ids = set(ident["TransactionID"])

all_cols = pd.read_csv("data/transactions.csv", nrows=0).columns
cols = [c for c in all_cols if not (c.startswith("V") and c[1:].isdigit())]   # drop V1-V339
dev_cols = ["TransactionID", "customer_id", "ts", "channel", "risk_score",
            "TransactionAmt", "ProductCD", "addr1", "R_emaildomain"]
ident_keep = ["TransactionID", "DeviceType", "DeviceInfo", "id_15", "id_23", "id_30", "id_31", "id_33"]

s1, s2 = [], []
for chunk in pd.read_csv("data/transactions.csv", usecols=cols, chunksize=200_000):
    s1.append(chunk[chunk["customer_id"].isin(customers)])
    s2.append(chunk.loc[chunk["TransactionID"].isin(ident_ids), dev_cols])

tx = pd.concat(s1, ignore_index=True).merge(ident, on="TransactionID", how="left")
tx.to_csv("data/slice_customers_noV.csv", index=False)

dev = pd.concat(s2, ignore_index=True).merge(ident[ident_keep], on="TransactionID", how="left")
dev.to_csv("data/slice_devices.csv", index=False)

print("customers slice:", tx.shape, "| customers:", tx["customer_id"].nunique())
print("devices slice:", dev.shape)
print("missing flagged txns (should be set()):", set(cases["flagged_txn_id"]) - set(tx["TransactionID"]))
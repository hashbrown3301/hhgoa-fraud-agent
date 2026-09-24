"""Turn our existing CSVs into vertex/edge files ready for Savanna's Load Data UI.
Run from the hhgoa folder: python prepare_graph_csvs.py
Output goes to graph_load/ - upload each file there and map to the matching vertex/edge type.
"""
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
from pathlib import Path
from agent.detectors import load_transactions, add_profile

OUT = Path("graph_load")
OUT.mkdir(exist_ok=True)

tx = load_transactions("data/slice_customers_noV.csv")
cases = pd.read_csv("data/case_pack.csv")
closed = pd.read_csv("data/closed_cases_history.csv")

# ---------------- vertices ----------------
customers = pd.DataFrame({"id": sorted(tx["customer_id"].unique())})
customers.to_csv(OUT / "v_customer.csv", index=False)

cards = tx[["customer_id", "card4", "card6"]].drop_duplicates("customer_id").rename(columns={"customer_id": "id"})
cards["card_type"] = cards["card6"]
cards[["id", "card_type", "card4", "card6"]].to_csv(OUT / "v_card.csv", index=False)

txns = tx[["txn", "ts", "channel", "TransactionAmt", "ProductCD", "addr1", "addr2", "risk_score"]].copy()
txns.columns = ["id", "ts", "channel", "amt", "product", "addr1", "addr2", "risk_score"]
txns["ts"] = txns["ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
txns.to_csv(OUT / "v_txn.csv", index=False)

dev = tx[tx["profile"] != ""][["profile", "DeviceType", "id_15", "id_23"]].drop_duplicates("profile")
dev.columns = ["id", "device_type", "new_flag", "proxy_ip"]
dev.to_csv(OUT / "v_deviceprofile.csv", index=False)

regions = tx.loc[(tx["channel"] == "in_person") & tx["addr1"].notna(), "addr1"].astype(str).drop_duplicates()
pd.DataFrame({"id": sorted(regions.unique())}).to_csv(OUT / "v_region.csv", index=False)

cc = closed.copy()
cc["id"] = cc["case_id"]
cc[["id", "customer_id", "card_id", "outcome", "pattern", "exposure_usd", "n_txns",
    "report_filed", "analyst_notes", "opened_at"]].to_csv(OUT / "v_closedcase.csv", index=False)

# ---------------- edges ----------------
pd.DataFrame({"from": tx["customer_id"], "to": tx["customer_id"]}).drop_duplicates() \
    .to_csv(OUT / "e_owns.csv", index=False)

pd.DataFrame({"from": tx["customer_id"], "to": tx["txn"]}) \
    .to_csv(OUT / "e_made.csv", index=False)

ud = tx[tx["profile"] != ""][["txn", "profile"]].rename(columns={"txn": "from", "profile": "to"})
ud.to_csv(OUT / "e_used_device.csv", index=False)

ar = tx[(tx["channel"] == "in_person") & tx["addr1"].notna()][["txn", "addr1"]]
ar["addr1"] = ar["addr1"].astype(str)
ar.columns = ["from", "to"]
ar.to_csv(OUT / "e_at_region.csv", index=False)

cocard = cc[["id", "card_id"]].rename(columns={"id": "from", "card_id": "to"})
cocard.to_csv(OUT / "e_closed_on_card.csv", index=False)

tx_prof = dict(zip(tx["txn"], tx["profile"]))
def first_txn(row):
    if pd.notna(row.get("first_fraud_txn_id")):
        return str(int(row["first_fraud_txn_id"]))
    ids = str(row.get("txn_ids", "")).split("|")
    return ids[0] if ids and ids[0] not in ("", "nan") else None

rows = []
for _, r in cc.iterrows():
    t = first_txn(r)
    prof = tx_prof.get(t) if t else None
    if prof:
        rows.append({"from": r["id"], "to": prof})
pd.DataFrame(rows).drop_duplicates().to_csv(OUT / "e_closed_used_device.csv", index=False)

print("Done. Files written to graph_load/:")
for p in sorted(OUT.glob("*.csv")):
    n = sum(1 for _ in open(p, encoding="utf-8")) - 1
    print(f"  {p.name:28s} {n} rows")
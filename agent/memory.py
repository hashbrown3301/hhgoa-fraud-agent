"""Case memory: retrieve similar closed cases (TF-IDF prototype).

TigerGraph's vector store replaces the TF-IDF index later (same interface: text in,
ranked closed cases out). Closed cases are matched on BEHAVIOUR text, never on the
alert trigger: in the history every confirmed fraud was customer-reported and every
cleared case was a model alert, so 'trigger type' would leak the answer wrongly.
Use it to CITE similar cases; do not read a probability off it (see model.py).
"""
import re
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

TARGET_FRAUD_RATE = 0.50      # README: "Half the cases are legitimate"


def normalise(note):
    """Strip ids, dates and amounts so retrieval keys on behaviour, not on who/when."""
    s = re.sub(r"CC-\d+", " ", str(note))
    s = re.sub(r"C\d{5}(-K\d)?", " ", s)
    s = re.sub(r"\d{4}-\d{2}-\d{2}", " ", s)
    s = re.sub(r"\$?[\d,]+\.?\d*", " ", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def prior_shift(p, from_rate, to_rate=TARGET_FRAUD_RATE):
    """Re-express a probability learned where fraud is `from_rate` for a pool where it is `to_rate`."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    odds = p / (1 - p) * (to_rate / (1 - to_rate)) / (from_rate / (1 - from_rate))
    return odds / (1 + odds)


class CaseMemory:
    def __init__(self, closed_csv=None, df=None):
        self.df = (df if df is not None else pd.read_csv(closed_csv)).copy()
        self.df["opened_at"] = pd.to_datetime(self.df["opened_at"])
        self.df["fraud"] = (self.df["outcome"] == "confirmed_fraud").astype(int)
        self._fit()

    def _fit(self):
        self.df = self.df.reset_index(drop=True)
        self.docs = [normalise(n) + " pattern " + str(p) for n, p in zip(self.df["analyst_notes"], self.df["pattern"])]
        self.vec = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=1)
        self.mat = self.vec.fit_transform(self.docs)
        self.fraud_rate = float(self.df["fraud"].mean())

    # ---- retrieval
    def similar(self, query, k=5, as_of=None, exclude_customer=None):
        """Top-k closed cases by text similarity. `as_of` keeps memory honest: only cases
        already opened before the alert can be used."""
        q = self.vec.transform([normalise(query)])
        sims = linear_kernel(q, self.mat).ravel()
        mask = np.ones(len(self.df), dtype=bool)
        if as_of is not None:
            mask &= (self.df["opened_at"] <= pd.Timestamp(as_of)).to_numpy()
        if exclude_customer is not None:
            mask &= (self.df["customer_id"] != exclude_customer).to_numpy()
        sims = np.where(mask, sims, -1)
        idx = np.argsort(-sims)[:k]
        return [self._row(i, sims[i]) for i in idx if sims[i] > 0]

    def _row(self, i, sim):
        r = self.df.iloc[i]
        return {"case_id": r["case_id"], "similarity": round(float(sim), 3), "outcome": r["outcome"],
                "pattern": r["pattern"], "exposure_usd": float(r["exposure_usd"]),
                "actions": r["actions_taken"], "report_filed": r["report_filed"],
                "customer_id": r["customer_id"], "note": r["analyst_notes"]}

    def by_customer(self, customer_id, as_of=None):
        d = self.df[self.df["customer_id"] == customer_id]
        if as_of is not None:
            d = d[d["opened_at"] <= pd.Timestamp(as_of)]
        return [self._row(self.df.index.get_loc(i), 1.0) for i in d.index]

    def token_cases(self, token, as_of=None):
        """Closed cases whose note mentions an exact token, e.g. a device model 'SM-G935F'."""
        m = self.df["analyst_notes"].str.contains(re.escape(token), case=False, na=False)
        if as_of is not None:
            m &= self.df["opened_at"] <= pd.Timestamp(as_of)
        return [self._row(i, 1.0) for i in self.df.index[m]]

    # ---- summaries the agent can cite
    def outcome_mix(self, cases):
        n = len(cases)
        if not n:
            return {"n": 0, "fraud_share": None, "adjusted_fraud_share": None}
        share = float(np.mean([c["outcome"] == "confirmed_fraud" for c in cases]))
        return {"n": n, "fraud_share": round(share, 3),
                "adjusted_fraud_share": round(prior_shift(share, self.fraud_rate), 3),
                "patterns": pd.Series([c["pattern"] for c in cases]).value_counts().to_dict()}

    def pattern_stats(self):
        g = self.df.groupby("pattern").agg(
            n=("case_id", "size"), fraud_share=("fraud", "mean"),
            median_exposure=("exposure_usd", "median"), median_txns=("n_txns", "median"),
            report_rate=("report_filed", lambda s: float((s == "Yes").mean())))
        return g.round(3)

    # ---- write-back (case memory grows as cases are resolved)
    def add_case(self, case_id, customer_id, card_id, opened_at, outcome, pattern,
                 txn_ids, exposure_usd, actions_taken, report_filed, analyst_notes,
                 connected_card_ids=""):
        row = {"case_id": case_id, "customer_id": customer_id, "card_id": card_id,
               "opened_at": opened_at, "closed_at": opened_at, "outcome": outcome, "pattern": pattern,
               "first_fraud_txn_id": (txn_ids[0] if txn_ids else np.nan), "txn_ids": "|".join(txn_ids),
               "n_txns": len(txn_ids), "exposure_usd": exposure_usd, "connected_card_ids": connected_card_ids,
               "actions_taken": actions_taken, "report_filed": report_filed, "analyst_notes": analyst_notes}
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)
        self.df["opened_at"] = pd.to_datetime(self.df["opened_at"])
        self.df["fraud"] = (self.df["outcome"] == "confirmed_fraud").astype(int)
        self._fit()


# ---- turn detector facts into text that speaks the analysts' vocabulary
def describe_facts(f):
    """Behaviour description built ONLY from facts. It never says 'confirmed' or 'denied'."""
    parts = []
    fl, reg, dev, ep = f["flagged"], f["region"], f["device"], f["episode"]
    if fl["channel"] == "online":
        parts.append("online purchases")
        if dev["marked_new"] or (dev["profile"] and not dev["profile_seen_before"]):
            parts.append("from a device not previously seen on this account")
        if "new_product" in fl["flags"] or "amount_outlier" in fl["flags"] or "rare_channel" in fl["flags"]:
            parts.append("inconsistent with the cardholder's usual merchants and amounts")
        if dev["proxy"]:
            parts.append("behind an anonymous proxy" if "ANONYMOUS" in dev["proxy"] else "behind a proxy")
        if dev["profile"]:
            parts.append("came from " + dev["profile"].replace("|", " on ", 1).replace("|", " "))
    else:
        parts.append("card-present purchase")
        if reg["prior_visits"] == 0:
            parts.append("in a billing region the cardholder had no history in")
        elif reg["routine"]:
            parts.append("in a billing region the cardholder visits regularly, amount typical")
    if f["card_testing"]["detected"]:
        parts.append("a run of very small online authorizations followed by a larger purchase, testing a stolen card number")
    if len(ep["txn_ids"]) >= 3:
        parts.append("multiple transactions in a short burst")
    if f.get("shared_device", {}).get("ring_like"):
        parts.append("same device profile reported by other cardholders")
    return "; ".join(parts)
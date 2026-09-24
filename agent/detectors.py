"""Pattern detectors + episode finder (pandas prototype).

Everything here is deterministic and returns plain facts (no verdicts, no weights).
The agent/LLM reads these facts; policy.py decides routes. These same checks get
ported to GSQL later - keep each function small so it maps to one query.

Card note: transactions carry customer_id but no card_id, and in this data each
customer has one card1 value, so "card history" == the customer's rows.
"""
import numpy as np
import pandas as pd

PROFILE_COLS = ["DeviceInfo", "id_30", "id_31", "id_33"]   # README: device profile
SMALL_AMT = 5.0            # README pattern 1: "often under $5"
BURST_HOURS = 1            # R5: within an hour
EPISODE_HOURS = 48         # README pattern 2: burst within 48 hours
CHAIN_GAP_HOURS = 6        # suspicious txns closer than this join one episode
ROUTINE_MIN_VISITS = 6     # a region visited this often is part of the routine
ROUTINE_MIN_WEEKS = 4


# ----------------------------------------------------------------- loading
def add_profile(df):
    parts = [df[c].fillna("").astype(str) for c in PROFILE_COLS]
    prof = parts[0] + " | " + parts[1] + " | " + parts[2] + " | " + parts[3]
    df["profile"] = prof.where(prof.str.replace(r"[\s|]", "", regex=True) != "", "")
    return df


def load_transactions(path):
    df = pd.read_csv(path, low_memory=False)
    df["ts"] = pd.to_datetime(df["ts"])
    df["txn"] = df["TransactionID"].astype(str)
    df = add_profile(df)
    return df.sort_values(["customer_id", "ts"]).reset_index(drop=True)


def visible(df, as_of=None):
    """Only what the bank knew when the alert opened (no peeking at later transactions)."""
    return df if as_of is None else df[df["ts"] <= pd.Timestamp(as_of)]


def customer_history(df, customer_id, as_of=None):
    h = df[df["customer_id"] == customer_id]
    return visible(h, as_of).sort_values("ts").reset_index(drop=True)


# ----------------------------------------------------------------- baseline
def baseline(h, cutoff):
    """What is normal for this card before `cutoff`."""
    p = h[h["ts"] < cutoff]
    inp = p[p["channel"] == "in_person"]
    return {
        "n": int(len(p)),
        "first_seen": str(p["ts"].min()) if len(p) else None,
        "online_share": round(float((p["channel"] == "online").mean()), 3) if len(p) else 0.0,
        "amt_median": round(float(p["TransactionAmt"].median()), 2) if len(p) else 0.0,
        "amt_p95": round(float(p["TransactionAmt"].quantile(0.95)), 2) if len(p) else 0.0,
        "amt_max": round(float(p["TransactionAmt"].max()), 2) if len(p) else 0.0,
        "products": {k: int(v) for k, v in p["ProductCD"].value_counts().items()},
        "regions": {str(k): int(v) for k, v in inp["addr1"].value_counts().items()},
        "profiles": sorted(set(p.loc[p["profile"] != "", "profile"])),
        "n_online": int((p["channel"] == "online").sum()),
    }


# ----------------------------------------------------------------- region / routine
def region_stats(h, row):
    """How established is this billing region for this card? (HHG-001 style check)"""
    prior = h[(h["ts"] < row["ts"]) & (h["addr1"] == row["addr1"])] if pd.notna(row["addr1"]) else h.iloc[0:0]
    n = len(prior)
    out = {"region": None if pd.isna(row["addr1"]) else str(row["addr1"]),
           "prior_visits": int(n), "distinct_days": 0, "distinct_weeks": 0,
           "first_seen": None, "last_seen": None, "same_weekday_share": 0.0,
           "median_gap_days": None, "routine": False}
    if n == 0:
        return out
    days = prior["ts"].dt.normalize()
    out.update(
        distinct_days=int(days.nunique()),
        distinct_weeks=int(prior["ts"].dt.to_period("W").nunique()),
        first_seen=str(prior["ts"].min()), last_seen=str(prior["ts"].max()),
        same_weekday_share=round(float((prior["ts"].dt.weekday == row["ts"].weekday()).mean()), 2),
    )
    d = days.drop_duplicates().sort_values().diff().dropna().dt.days
    if len(d):
        out["median_gap_days"] = float(d.median())
    out["routine"] = bool(n >= ROUTINE_MIN_VISITS and out["distinct_weeks"] >= ROUTINE_MIN_WEEKS)
    return out


def amount_recurrence(h, row, tol=0.10):
    """Same-ish amount seen before on this card (R7-style recurring charge check).
    `regular` requires >=4 occurrences with a fairly even gap between them (coefficient of
    variation <= 0.6), so a merchant-less proxy for "recurring" isn't satisfied by amounts
    that just happen to repeat inside a dense, irregular stream of purchases."""
    prior = h[h["ts"] < row["ts"]]
    amt = row["TransactionAmt"]
    sim = prior[(prior["TransactionAmt"] - amt).abs() <= tol * amt]
    same_region = sim[sim["addr1"] == row["addr1"]] if pd.notna(row["addr1"]) else sim.iloc[0:0]
    base_for_gap = same_region if len(same_region) >= 3 else sim
    regular, gap_mean, gap_std = False, None, None
    if len(base_for_gap) >= 3:
        gaps = base_for_gap["ts"].sort_values().diff().dropna().dt.total_seconds() / 86400
        if len(gaps) >= 2 and gaps.mean() > 0:
            gap_mean, gap_std = float(gaps.mean()), float(gaps.std())
            regular = bool(len(base_for_gap) >= 4 and (gap_std / gap_mean) <= 0.6)
    return {"similar_amount_prior": int(len(sim)),
            "similar_amount_same_region": int(len(same_region)),
            "share_of_history_with_similar_amount": round(len(sim) / max(len(prior), 1), 3),
            "regular": regular,
            "gap_days_mean": round(gap_mean, 1) if gap_mean is not None else None,
            "gap_days_std": round(gap_std, 1) if gap_std is not None else None}


# ----------------------------------------------------------------- pattern detectors
def card_testing(h, row, small=SMALL_AMT, lookaround_h=24):
    """Pattern 1 / R5: >=3 tiny online auths inside an hour, then a larger purchase."""
    lo, hi = row["ts"] - pd.Timedelta(hours=lookaround_h), row["ts"] + pd.Timedelta(hours=lookaround_h)
    w = h[(h["ts"] >= lo) & (h["ts"] <= hi) & (h["channel"] == "online")]
    tiny = w[w["TransactionAmt"] < small]
    best = None
    for _, t in tiny.iterrows():
        burst = tiny[(tiny["ts"] >= t["ts"]) & (tiny["ts"] <= t["ts"] + pd.Timedelta(hours=BURST_HOURS))]
        if len(burst) >= 3:
            last = burst["ts"].max()
            after = w[(w["ts"] > last) & (w["ts"] <= last + pd.Timedelta(hours=3)) & (w["TransactionAmt"] >= small)]
            if len(after):
                best = {"detected": True, "tiny_ids": list(burst["txn"]),
                        "followup_ids": list(after["txn"]),
                        "followup_max_amt": float(after["TransactionAmt"].max())}
                break
    return best or {"detected": False, "tiny_ids": [], "followup_ids": [], "followup_max_amt": 0.0}


def device_signals(h, row, before=None):
    """Pattern 3: device marked New / unseen profile / proxy. Not proof: people buy new phones.
    `before` = start of the episode, so earlier txns of the same burst don't make the device look known."""
    prior = h[h["ts"] < (before if before is not None else row["ts"])]
    prof = row.get("profile", "") or ""
    return {
        "has_identity": bool(prof) or pd.notna(row.get("id_15")),
        "profile": prof,
        "marked_new": bool(row.get("id_15") == "New"),
        "profile_seen_before": bool(prof) and bool((prior["profile"] == prof).any()),
        "proxy": None if pd.isna(row.get("id_23")) else str(row["id_23"]),
        "device_type": None if pd.isna(row.get("DeviceType")) else str(row["DeviceType"]),
    }


def txn_flags(row, base, prior_h):
    """Per-transaction deviations from the card's own baseline (facts, not points)."""
    f = []
    online = row["channel"] == "online"
    if not online and pd.notna(row["addr1"]) and str(row["addr1"]) not in base["regions"]:
        f.append("new_region")
    if base["n"] >= 10 and row["ProductCD"] not in base["products"]:
        f.append("new_product")
    if base["n"] >= 10 and row["TransactionAmt"] > max(3 * base["amt_p95"], 100):
        f.append("amount_outlier")
    if online and row.get("id_15") == "New":
        f.append("new_device")
    if online and pd.notna(row.get("id_23")):
        f.append("proxy")
    if online and row["TransactionAmt"] < SMALL_AMT:
        f.append("tiny_online")
    if online and base["n"] >= 10 and base["online_share"] < 0.10:
        f.append("rare_channel")
    return f


# ----------------------------------------------------------------- episode finder
def find_episode(h, row, window_h=EPISODE_HOURS, max_gap_h=CHAIN_GAP_HOURS):
    """Chain the flagged txn to nearby txns that deviate from the card's baseline in the
    same way (share a flag) and sit within max_gap_h of the chain. Baseline is taken BEFORE
    the window so the episode cannot hide itself. A flagged txn with no deviation stays alone:
    nearby oddities are reported separately, not silently merged."""
    win_lo = row["ts"] - pd.Timedelta(hours=window_h)
    base = baseline(h, win_lo)
    win = h[(h["ts"] >= win_lo) & (h["ts"] <= row["ts"] + pd.Timedelta(hours=window_h))].copy()
    win["flags"] = [txn_flags(r, base, h) for _, r in win.iterrows()]
    info = {r["txn"]: (r["ts"], set(r["flags"])) for _, r in win.iterrows()}
    chain = [row["txn"]]
    chain_flags = set(info[row["txn"]][1])
    changed = bool(chain_flags)
    while changed:
        changed = False
        for t, (ts, fl) in info.items():
            if t in chain or not fl or not (fl & chain_flags):
                continue
            if any(abs((ts - info[c][0]).total_seconds()) <= max_gap_h * 3600 for c in chain):
                chain.append(t); chain_flags |= fl; changed = True
    ep = win[win["txn"].isin(chain)].sort_values("ts")
    others = win[(win["flags"].str.len() > 0) & (~win["txn"].isin(chain))].sort_values("ts")
    return {
        "txn_ids": list(ep["txn"]),
        "first_txn_id": ep.iloc[0]["txn"],
        "exposure_usd": round(float(ep["TransactionAmt"].abs().sum()), 2),
        "start": str(ep["ts"].min()), "end": str(ep["ts"].max()),
        "flags_by_txn": {r["txn"]: r["flags"] for _, r in ep.iterrows()},
        "deviating_txns": int((ep["flags"].str.len() > 0).sum()),
        "nearby_other_suspicious": list(others["txn"]),
        "baseline_used": {k: base[k] for k in ("n", "amt_median", "amt_p95", "online_share", "products")},
    }


# ----------------------------------------------------------------- other cards (rings)
RING_MIN_CUSTOMERS = 10    # tuned on this data: profiles this widespread AND always "New"
RING_MIN_NEW_RATE = 0.95   # are rare; normal shared profiles (iPhones, Macs) fall below this


def profile_stats(light, prof):
    same = light[light["profile"] == prof]
    n = len(same)
    return {"n_customers": int(same["customer_id"].nunique()), "n_txns": int(n),
            "new_rate": round(float((same["id_15"] == "New").mean()), 3) if n else 0.0,
            "first": str(same["ts"].min()) if n else None, "last": str(same["ts"].max()) if n else None,
            "mean_risk_score": round(float(same["risk_score"].mean()), 3) if n else 0.0}


def shared_device(light, row, customer_id, window_days=30):
    """Other customers using the same device profile in a window around this txn,
    plus profile-level stats. `light` must already be cut at as_of."""
    prof = row.get("profile", "") or ""
    if not prof:
        return {"profile": "", "stats": None, "ring_like": False, "n_other_customers": 0, "other_customers": []}
    st = profile_stats(light, prof)
    same = light[light["profile"] == prof]
    win = same[(same["ts"] >= row["ts"] - pd.Timedelta(days=window_days)) &
               (same["ts"] <= row["ts"] + pd.Timedelta(days=window_days))]
    oth = win[win["customer_id"] != customer_id]
    rows = []
    for cid, g in oth.groupby("customer_id"):
        rows.append({"customer_id": cid, "n_txns": int(len(g)),
                     "n_marked_new": int((g["id_15"] == "New").sum()),
                     "first": str(g["ts"].min()), "last": str(g["ts"].max()),
                     "total_usd": round(float(g["TransactionAmt"].sum()), 2)})
    rows.sort(key=lambda r: (-r["n_marked_new"], -r["n_txns"]))
    ring = st["n_customers"] >= RING_MIN_CUSTOMERS and st["new_rate"] >= RING_MIN_NEW_RATE
    return {"profile": prof, "stats": st, "ring_like": bool(ring),
            "n_other_customers": len(rows), "other_customers": rows[:15]}


def ring_profiles(light):
    """Scan (Idea 2 / monitoring): device profiles used by many cards that are ALWAYS marked New."""
    on = light[light["profile"] != ""]
    g = on.groupby("profile").agg(n_customers=("customer_id", "nunique"), n_txns=("customer_id", "size"),
                                  new_rate=("id_15", lambda x: float((x == "New").mean())),
                                  first=("ts", "min"), last=("ts", "max"),
                                  mean_risk_score=("risk_score", "mean"), total_usd=("TransactionAmt", "sum"))
    return g[(g["n_customers"] >= RING_MIN_CUSTOMERS) & (g["new_rate"] >= RING_MIN_NEW_RATE)] \
        .sort_values("n_customers", ascending=False)


def shared_email(light, row, customer_id, window_days=30, rare_max_customers=25):
    """Same recipient email domain across cards - only meaningful when the domain is rare."""
    dom = row.get("R_emaildomain")
    if pd.isna(dom):
        return {"domain": None, "n_total_customers": 0, "other_customers": []}
    same = light[light["R_emaildomain"] == dom]
    n_tot = int(same["customer_id"].nunique())
    win = same[(same["ts"] >= row["ts"] - pd.Timedelta(days=window_days)) &
               (same["ts"] <= row["ts"] + pd.Timedelta(days=window_days))]
    oth = sorted(set(win["customer_id"]) - {customer_id})
    return {"domain": str(dom), "n_total_customers": n_tot,
            "rare": n_tot <= rare_max_customers, "other_customers": oth[:15]}


# ----------------------------------------------------------------- one call = evidence bundle
def gather_facts(hist, flagged_txn_id, light=None, as_of=None):
    """Everything the agent needs about one alert, as plain JSON-able facts."""
    hist = visible(hist, as_of)
    light = visible(light, as_of) if light is not None else None
    row = hist[hist["txn"] == str(flagged_txn_id)]
    if row.empty:
        raise KeyError(f"transaction {flagged_txn_id} not in history")
    row = row.iloc[0]
    episode = find_episode(hist, row)
    facts = {
        "flagged": {"txn": row["txn"], "ts": str(row["ts"]), "channel": row["channel"],
                    "amount": float(row["TransactionAmt"]), "product": row["ProductCD"],
                    "region": None if pd.isna(row["addr1"]) else str(row["addr1"]),
                    "risk_score": float(row["risk_score"])},
        "baseline": baseline(hist, row["ts"]),
        "region": region_stats(hist, row),
        "amount_recurrence": amount_recurrence(hist, row),
        "card_testing": card_testing(hist, row),
        "device": device_signals(hist, row, before=pd.Timestamp(episode["start"])),
        "episode": episode,
    }
    facts["flagged"]["flags"] = txn_flags(row, baseline(hist, row["ts"] - pd.Timedelta(hours=EPISODE_HOURS)), hist)
    if light is not None:
        facts["shared_device"] = shared_device(light, row, row["customer_id"])
        facts["shared_email"] = shared_email(light, row, row["customer_id"])
    return facts
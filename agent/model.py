"""Calibrated fraud probability from behaviour features (trained on closed cases)."""
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.metrics import roc_auc_score, brier_score_loss
from .features import FEATURES
from .memory import prior_shift, TARGET_FRAUD_RATE


def make_model():
    return make_pipeline(StandardScaler(), LogisticRegression(C=0.5, max_iter=2000, class_weight=None))


def evaluate(feat_df, folds=5):
    """Cross-validated AUC / Brier so you know how much to trust the probability."""
    X, y = feat_df[FEATURES].to_numpy(), feat_df["fraud"].to_numpy()
    k = int(min(folds, y.sum(), (1 - y).sum()))
    if k < 2:
        return {"error": "need at least 2 cases of each class"}
    p = cross_val_predict(make_model(), X, y, cv=StratifiedKFold(k, shuffle=True, random_state=0),
                          method="predict_proba")[:, 1]
    return {"n": int(len(y)), "fraud_rate": round(float(y.mean()), 3), "auc": round(float(roc_auc_score(y, p)), 3),
            "brier": round(float(brier_score_loss(y, p)), 4)}


def fit(feat_df):
    m = make_model()
    m.fit(feat_df[FEATURES].to_numpy(), feat_df["fraud"].to_numpy())
    m.train_fraud_rate_ = float(feat_df["fraud"].mean())
    return m


def predict(model, feats, target_rate=TARGET_FRAUD_RATE):
    """Probability re-based to the benchmark's ~50% fraud rate (history is ~84% fraud)."""
    p = float(model.predict_proba(pd.DataFrame([feats])[FEATURES].to_numpy())[0, 1])
    return round(prior_shift(p, model.train_fraud_rate_, target_rate), 3)


def explain(model, feats):
    """Which features pushed the score, for the case file (linear model = honest attribution)."""
    scaler, lr = model.named_steps["standardscaler"], model.named_steps["logisticregression"]
    z = scaler.transform(pd.DataFrame([feats])[FEATURES].to_numpy())[0] * lr.coef_[0]
    order = np.argsort(-np.abs(z))[:5]
    return [(FEATURES[i], round(float(z[i]), 2)) for i in order]
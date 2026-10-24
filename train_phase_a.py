"""
Phase A Upgrade ? Retrain Model C with:
  + 3 new features (max-pain distance, ATM IV, time-to-expiry)
  + Triple-barrier labeling
  + Purged walk-forward validation

Saves to models/xgb_volatility_v3.json ? does NOT overwrite v1
"""
import pandas as pd
import numpy as np
import pickle
import xgboost as xgb
from pathlib import Path
from datetime import datetime
from sklearn.metrics import accuracy_score, classification_report

DATA_DIR = Path("data/historical")
MODEL_DIR = Path("models")

print("=" * 60)
print("  PHASE A ? Model C v3 Training")
print("=" * 60)

# ============================================================
# LOAD
# ============================================================
print("\n[1/6] Loading historical data...")
opt = pd.read_parquet(DATA_DIR / "nifty_options_3y.parquet")
spot = pd.read_parquet(DATA_DIR / "nifty_spot_3y.parquet")
print(f"Options: {len(opt):,} rows")
print(f"Spot:    {len(spot):,} rows")

opt["datetime"] = pd.to_datetime(opt["datetime"])
spot["datetime"] = pd.to_datetime(spot["datetime"])
opt["right"] = opt["right"].str.lower()
opt["strike"] = opt["strike"].astype(float)
opt["expiry"] = pd.to_datetime(opt["expiry"])

# Sample every 5 min
unique_min = sorted(opt["datetime"].unique())
sample_min = unique_min[::5]
opt = opt[opt["datetime"].isin(sample_min)]
print(f"Sampled: {len(opt):,} rows")

# ============================================================
# FEATURE ENGINEERING ? 9 FEATURES (3 NEW)
# ============================================================
print("\n[2/6] Building 9 features (6 original + 3 new)...")

rows = []
for (ts, exp), grp in opt.groupby(["datetime", "expiry"]):
    calls = grp[grp["right"] == "call"]
    puts = grp[grp["right"] == "put"]
    if len(calls) < 3 or len(puts) < 3:
        continue

    merged = calls[["strike", "close"]].rename(columns={"close": "c"}).merge(
        puts[["strike", "close"]].rename(columns={"close": "p"}), on="strike"
    )
    if len(merged) < 3:
        continue
    merged["d"] = (merged["c"] - merged["p"]).abs()
    atm = merged.loc[merged["d"].idxmin()]
    implied_spot = atm["strike"] + atm["c"] - atm["p"]
    if implied_spot <= 0:
        continue

    # --- Original 6 features ---
    pcr = puts["open_interest"].sum() / max(calls["open_interest"].sum(), 1)
    vol_ratio = puts["volume"].sum() / max(calls["volume"].sum(), 1)
    straddle = float(atm["c"] + atm["p"])
    call_wall = float(calls.nlargest(1, "open_interest")["strike"].iloc[0])
    put_wall = float(puts.nlargest(1, "open_interest")["strike"].iloc[0])
    wall_asym = (put_wall - call_wall) / max(implied_spot, 1)

    # --- NEW FEATURE 1: Max-pain distance ---
    strikes = grp["strike"].unique()
    pain_values = []
    for s in strikes:
        c_pain = ((s - grp[grp["right"] == "call"]["strike"]).clip(lower=0) *
                  grp[grp["right"] == "call"]["open_interest"]).sum()
        p_pain = ((grp[grp["right"] == "put"]["strike"] - s).clip(lower=0) *
                  grp[grp["right"] == "put"]["open_interest"]).sum()
        pain_values.append(c_pain + p_pain)
    if len(pain_values) > 0:
        max_pain = strikes[int(np.argmin(pain_values))]
        max_pain_dist = (max_pain - implied_spot) / implied_spot
    else:
        max_pain_dist = 0.0

    # --- NEW FEATURE 2: ATM IV (avg call/put IV at ATM) ---
    atm_call_iv = float(atm.get("c_iv", 0)) if "c_iv" in atm else 0.0
    atm_put_iv = float(atm.get("p_iv", 0)) if "p_iv" in atm else 0.0
    # Fallback: use closest call/put IV columns
    try:
        atm_strike = float(atm["strike"])
        atm_call_row = calls[calls["strike"] == atm_strike]
        atm_put_row = puts[puts["strike"] == atm_strike]
        if len(atm_call_row) and "call_iv" in atm_call_row.columns:
            atm_call_iv = float(atm_call_row["call_iv"].iloc[0])
        if len(atm_put_row) and "put_iv" in atm_put_row.columns:
            atm_put_iv = float(atm_put_row["put_iv"].iloc[0])
    except Exception:
        pass
    atm_iv = (atm_call_iv + atm_put_iv) / 2.0

    # --- NEW FEATURE 3: Time-to-expiry (days) ---
    try:
        dte = (exp - ts).total_seconds() / 86400.0
    except Exception:
        dte = 0.0

    rows.append({
        "datetime": ts,
        "implied_spot": implied_spot,
        "pcr": pcr,
        "vol_ratio": vol_ratio,
        "straddle": straddle,
        "wall_asym": wall_asym,
        "max_pain_dist": max_pain_dist,
        "atm_iv": atm_iv,
        "days_to_expiry": dte,
    })

feat = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
print(f"Feature rows: {len(feat):,}")

# Momentum (using implied spot)
feat["spot"] = feat["implied_spot"]
feat["mom_5m"] = (feat["spot"] - feat["spot"].shift(1)) / feat["spot"].shift(1)
feat["mom_15m"] = (feat["spot"] - feat["spot"].shift(3)) / feat["spot"].shift(3)

# ============================================================
# TRIPLE-BARRIER LABELING
# ============================================================
print("\n[3/6] Triple-barrier labeling...")

UP_BARRIER = 0.0015    # +0.15% (approx 30 pts on 20,000)
DOWN_BARRIER = 0.0010  # -0.10% (approx 20 pts)
TIME_BARRIER = 6       # 30 min (6 ? 5-min steps)

def triple_barrier_label(prices, i, up, down, max_steps):
    """
    Returns: 1 if upper hit first, 0 if lower hit first, 2 if time barrier.
    """
    entry = prices[i]
    for step in range(1, max_steps + 1):
        if i + step >= len(prices):
            return 2
        cur = prices[i + step]
        ret = (cur - entry) / entry
        if ret >= up:
            return 1  # up barrier
        if ret <= -down:
            return 0  # down barrier
    return 2  # time barrier

prices = feat["spot"].values
labels = []
for i in range(len(prices) - TIME_BARRIER):
    labels.append(triple_barrier_label(prices, i, UP_BARRIER, DOWN_BARRIER, TIME_BARRIER))
labels.extend([2] * TIME_BARRIER)
feat["label"] = labels

# For binary classification, keep only direction-barrier outcomes
feat_binary = feat[feat["label"] != 2].copy()
feat_binary = feat_binary.dropna().reset_index(drop=True)

print(f"Total with triple-barrier labels: {len(feat):,}")
print(f"Up barrier hits:     {(feat['label'] == 1).sum():,}")
print(f"Down barrier hits:   {(feat['label'] == 0).sum():,}")
print(f"Time barrier (skip): {(feat['label'] == 2).sum():,}")
print(f"Binary classification samples: {len(feat_binary):,}")

# ============================================================
# PURGED WALK-FORWARD CV
# ============================================================
print("\n[4/6] Purged walk-forward CV...")

FEATURES = ["pcr", "vol_ratio", "straddle", "wall_asym",
            "max_pain_dist", "atm_iv", "days_to_expiry",
            "mom_5m", "mom_15m"]

X = feat_binary[FEATURES].values
y = feat_binary["label"].values

# Purged walk-forward: 4 folds, purge gap of 5 samples between train/test
n = len(X)
n_folds = 4
fold_size = n // (n_folds + 1)
PURGE = 10  # samples purged between train and test

fold_accuracies = []
for fold in range(n_folds):
    train_end = fold_size * (fold + 1)
    test_start = train_end + PURGE
    test_end = min(test_start + fold_size, n)
    if test_end <= test_start:
        continue

    X_train, y_train = X[:train_end], y[:train_end]
    X_test, y_test = X[test_start:test_end], y[test_start:test_end]

    model = xgb.XGBClassifier(
        n_estimators=300, max_depth=4, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, eval_metric="logloss",
    )
    model.fit(X_train, y_train)
    acc = accuracy_score(y_test, model.predict(X_test))
    fold_accuracies.append(acc)
    print(f"  Fold {fold+1}: train={len(X_train):,}  test={len(X_test):,}  acc={acc:.4f}")

if fold_accuracies:
    mean_acc = float(np.mean(fold_accuracies))
    std_acc = float(np.std(fold_accuracies))
    print(f"\n  Mean accuracy: {mean_acc:.4f} (+/- {std_acc:.4f})")
else:
    mean_acc = 0.0
    print("  No folds ran.")

# ============================================================
# FINAL MODEL ? Full data
# ============================================================
print("\n[5/6] Training final v3 model on all data...")

# Time-ordered 80/20 for final validation
split = int(len(X) * 0.8)
model_v3 = xgb.XGBClassifier(
    n_estimators=300, max_depth=4, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    random_state=42, n_jobs=-1, eval_metric="logloss",
)
model_v3.fit(X[:split], y[:split])
preds = model_v3.predict(X[split:])
final_acc = accuracy_score(y[split:], preds)

print(f"\n  Final 80/20 accuracy: {final_acc:.4f}")
print(classification_report(y[split:], preds, target_names=["DOWN", "UP"]))
print("Feature importance:")
for n_, i in zip(FEATURES, model_v3.feature_importances_):
    print(f"  {n_}: {i:.4f}")

# ============================================================
# SAVE
# ============================================================
print("\n[6/6] Saving v3 model...")
model_v3.save_model(str(MODEL_DIR / "xgb_volatility_v3.json"))
with open(MODEL_DIR / "xgb_volatility_v3.pkl", "wb") as f:
    pickle.dump({"model": model_v3, "features": FEATURES}, f)

# Also save feature list separately for the live agent
(MODEL_DIR / "features_v3.txt").write_text("\n".join(FEATURES))

print(f"[saved] models/xgb_volatility_v3.json")
print(f"[saved] models/xgb_volatility_v3.pkl")
print(f"[saved] models/features_v3.txt")

print("\n" + "=" * 60)
print("  PHASE A COMPLETE")
print("=" * 60)
print(f"  v3 accuracy (80/20):  {final_acc:.4f}")
print(f"  v3 accuracy (purged): {mean_acc:.4f} (+/- {std_acc:.4f})")
print(f"  Total features:       {len(FEATURES)}")
print(f"  Training samples:     {len(X):,}")

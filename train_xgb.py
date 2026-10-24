"""
Nifty Agent ? XGBoost Training
Loads option chain + Nifty spot. Trains a classifier.
"""
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb

DATA_DIR = Path("data/historical")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

print("[1/5] Loading option data...")
opt = pd.read_parquet(DATA_DIR / "nifty_options_3y.parquet")
print(f"      {len(opt):,} rows")

print("[2/5] Loading Nifty spot...")
spot = pd.read_parquet(DATA_DIR / "nifty_spot_3y.parquet")
print(f"      {len(spot):,} rows")

# Clean
opt["datetime"] = pd.to_datetime(opt["datetime"])
spot["datetime"] = pd.to_datetime(spot["datetime"])
opt["right"] = opt["right"].str.lower()
opt["strike"] = opt["strike"].astype(float)

# Sample minutes (every 5 min)
unique_min = sorted(opt["datetime"].unique())
sample_min = unique_min[::5]
opt = opt[opt["datetime"].isin(sample_min)]
print(f"      Sampled: {len(opt):,} rows across {len(sample_min)} minutes")

# ============================================================
# Feature engineering per (datetime, expiry)
# ============================================================
print("[3/5] Building features...")
rows = []

for (dt, exp), grp in opt.groupby(["datetime", "expiry"]):
    calls = grp[grp["right"] == "call"]
    puts  = grp[grp["right"] == "put"]
    if len(calls) < 3 or len(puts) < 3:
        continue

    # Implied spot via ATM strike
    merged = calls[["strike", "close"]].rename(columns={"close": "c"}).merge(
        puts[["strike", "close"]].rename(columns={"close": "p"}), on="strike"
    )
    if len(merged) < 3:
        continue
    merged["d"] = (merged["c"] - merged["p"]).abs()
    atm = merged.loc[merged["d"].idxmin()]
    implied_spot = atm["strike"] + atm["c"] - atm["p"]

    pcr = puts["open_interest"].sum() / max(calls["open_interest"].sum(), 1)
    vol_ratio = puts["volume"].sum() / max(calls["volume"].sum(), 1)
    straddle = float(atm["c"] + atm["p"])
    call_wall = float(calls.nlargest(1, "open_interest")["strike"].iloc[0])
    put_wall = float(puts.nlargest(1, "open_interest")["strike"].iloc[0])
    wall_asym = (put_wall - call_wall) / max(implied_spot, 1)

    rows.append({
        "datetime": dt,
        "implied_spot": implied_spot,
        "pcr": pcr,
        "vol_ratio": vol_ratio,
        "straddle": straddle,
        "wall_asym": wall_asym,
    })

feat = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
print(f"      {len(feat):,} feature rows")

# Merge with actual Nifty spot for momentum
spot_close = spot[["datetime", "close"]].rename(columns={"close": "spot"})
feat = feat.merge(spot_close, on="datetime", how="left")
feat["spot"] = feat["spot"].fillna(feat["implied_spot"])

# Momentum (5-min lookback ~ 1 step, 15-min ~ 3 steps)
feat["mom_5m"] = (feat["spot"] - feat["spot"].shift(1)) / feat["spot"].shift(1)
feat["mom_15m"] = (feat["spot"] - feat["spot"].shift(3)) / feat["spot"].shift(3)

# Target: Nifty up or down in next 5 min (1 step)
feat["next_spot"] = feat["spot"].shift(-1)
feat["label"] = (feat["next_spot"] > feat["spot"]).astype(int)

feat = feat.dropna().reset_index(drop=True)
print(f"      {len(feat):,} rows after labeling")

# ============================================================
# Train XGBoost
# ============================================================
print("[4/5] Training XGBoost...")
FEATURES = ["pcr", "vol_ratio", "straddle", "wall_asym", "mom_5m", "mom_15m"]

X = feat[FEATURES].values
y = feat["label"].values

# Time-ordered split (avoid lookahead)
split = int(len(X) * 0.8)
X_train, X_test = X[:split], X[split:]
y_train, y_test = y[:split], y[split:]

print(f"      Train: {len(X_train):,}  Test: {len(X_test):,}")

model = xgb.XGBClassifier(
    n_estimators=300,
    max_depth=4,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    random_state=42,
    n_jobs=-1,
    eval_metric="logloss",
)
model.fit(X_train, y_train)

preds = model.predict(X_test)
acc = accuracy_score(y_test, preds)

print(f"\n      ACCURACY: {acc:.4f}")
print(classification_report(y_test, preds, target_names=["DOWN", "UP"]))
print("Feature importance:")
for n, i in zip(FEATURES, model.feature_importances_):
    print(f"  {n}: {i:.4f}")

# Save
with open(MODEL_DIR / "xgb_nifty.pkl", "wb") as f:
    pickle.dump({"model": model, "features": FEATURES}, f)
print(f"\n[5/5] Model saved to models/xgb_nifty.pkl")

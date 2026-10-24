"""
Train both models:
  Model A ? 30-min direction (UP / DOWN)
  Model C ? 30-min volatility (BIG / SMALL move)
"""
import pandas as pd
import numpy as np
import pickle
from pathlib import Path
from sklearn.metrics import accuracy_score, classification_report
import xgboost as xgb

DATA_DIR = Path("data/historical")
MODEL_DIR = Path("models")
MODEL_DIR.mkdir(exist_ok=True)

print("=" * 60)
print("  LOADING DATA")
print("=" * 60)
opt = pd.read_parquet(DATA_DIR / "nifty_options_3y.parquet")
spot = pd.read_parquet(DATA_DIR / "nifty_spot_3y.parquet")
print(f"Options: {len(opt):,} rows")
print(f"Spot:    {len(spot):,} rows")

opt["datetime"] = pd.to_datetime(opt["datetime"])
spot["datetime"] = pd.to_datetime(spot["datetime"])
opt["right"] = opt["right"].str.lower()
opt["strike"] = opt["strike"].astype(float)

# Sample every 5 min
unique_min = sorted(opt["datetime"].unique())
sample_min = unique_min[::5]
opt = opt[opt["datetime"].isin(sample_min)]
print(f"Sampled: {len(opt):,} rows")

# ============================================================
print("\n" + "=" * 60)
print("  BUILDING FEATURES")
print("=" * 60)
rows = []
for (dt, exp), grp in opt.groupby(["datetime", "expiry"]):
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

    pcr = puts["open_interest"].sum() / max(calls["open_interest"].sum(), 1)
    vol_ratio = puts["volume"].sum() / max(calls["volume"].sum(), 1)
    straddle = float(atm["c"] + atm["p"])
    call_wall = float(calls.nlargest(1, "open_interest")["strike"].iloc[0])
    put_wall = float(puts.nlargest(1, "open_interest")["strike"].iloc[0])
    wall_asym = (put_wall - call_wall) / max(implied_spot, 1)

    rows.append({"datetime": dt, "implied_spot": implied_spot, "pcr": pcr,
                 "vol_ratio": vol_ratio, "straddle": straddle, "wall_asym": wall_asym})

feat = pd.DataFrame(rows).sort_values("datetime").reset_index(drop=True)
print(f"Feature rows: {len(feat):,}")

spot_close = spot[["datetime", "close"]].rename(columns={"close": "spot"})
feat = feat.merge(spot_close, on="datetime", how="left")
feat["spot"] = feat["spot"].fillna(feat["implied_spot"])

feat["mom_5m"] = (feat["spot"] - feat["spot"].shift(1)) / feat["spot"].shift(1)
feat["mom_15m"] = (feat["spot"] - feat["spot"].shift(3)) / feat["spot"].shift(3)

# ============================================================
# MODEL A ? 30-minute DIRECTION
# ============================================================
print("\n" + "=" * 60)
print("  MODEL A ? 30-minute Direction")
print("=" * 60)
feat_a = feat.copy()
feat_a["next_spot"] = feat_a["spot"].shift(-6)   # 30 min ahead
feat_a["label"] = (feat_a["next_spot"] > feat_a["spot"]).astype(int)
feat_a = feat_a.dropna().reset_index(drop=True)
print(f"Samples: {len(feat_a):,}")

FEATURES = ["pcr", "vol_ratio", "straddle", "wall_asym", "mom_5m", "mom_15m"]
X_a = feat_a[FEATURES].values
y_a = feat_a["label"].values
split = int(len(X_a) * 0.8)
model_a = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8,
                             random_state=42, n_jobs=-1, eval_metric="logloss")
model_a.fit(X_a[:split], y_a[:split])
preds_a = model_a.predict(X_a[split:])
acc_a = accuracy_score(y_a[split:], preds_a)
print(f"\n  ACCURACY: {acc_a:.4f}")
print(classification_report(y_a[split:], preds_a, target_names=["DOWN", "UP"]))
print("Feature importance:")
for n, i in zip(FEATURES, model_a.feature_importances_):
    print(f"  {n}: {i:.4f}")

pickle.dump({"model": model_a, "features": FEATURES},
            open(MODEL_DIR / "xgb_direction.pkl", "wb"))
print(f"[saved] models/xgb_direction.pkl")

# ============================================================
# MODEL C ? 30-minute VOLATILITY
# ============================================================
print("\n" + "=" * 60)
print("  MODEL C ? 30-minute Volatility")
print("=" * 60)
feat_c = feat.copy()
feat_c["next_spot"] = feat_c["spot"].shift(-6)
feat_c["move"] = (feat_c["next_spot"] - feat_c["spot"]).abs()
median_move = feat_c["move"].median()
print(f"Median 30-min move: {median_move:.1f} points")
feat_c["label"] = (feat_c["move"] > median_move).astype(int)
feat_c = feat_c.dropna().reset_index(drop=True)
print(f"Samples: {len(feat_c):,}")

X_c = feat_c[FEATURES].values
y_c = feat_c["label"].values
split = int(len(X_c) * 0.8)
model_c = xgb.XGBClassifier(n_estimators=300, max_depth=4, learning_rate=0.05,
                             subsample=0.8, colsample_bytree=0.8,
                             random_state=42, n_jobs=-1, eval_metric="logloss")
model_c.fit(X_c[:split], y_c[:split])
preds_c = model_c.predict(X_c[split:])
acc_c = accuracy_score(y_c[split:], preds_c)
print(f"\n  ACCURACY: {acc_c:.4f}")
print(classification_report(y_c[split:], preds_c, target_names=["SMALL", "BIG"]))
print("Feature importance:")
for n, i in zip(FEATURES, model_c.feature_importances_):
    print(f"  {n}: {i:.4f}")

pickle.dump({"model": model_c, "features": FEATURES},
            open(MODEL_DIR / "xgb_volatility.pkl", "wb"))
print(f"[saved] models/xgb_volatility.pkl")

# ============================================================
print("\n" + "=" * 60)
print("  SUMMARY")
print("=" * 60)
print(f"Model A (Direction):   {acc_a:.4f}  ({acc_a*100:.2f}%)")
print(f"Model C (Volatility):  {acc_c:.4f}  ({acc_c*100:.2f}%)")
print(f"\nBenchmark: 50% (random)")
print(f"Target:    >55% (useful), >60% (strong)")

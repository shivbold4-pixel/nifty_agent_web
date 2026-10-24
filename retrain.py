"""
Weekly retrain script ? pulls all labeled predictions from Supabase,
trains a fresh XGBoost model, and saves it.
Run manually: python retrain.py
"""
import os
import pickle
import numpy as np
from pathlib import Path
from datetime import datetime, timezone, timedelta
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
from supabase import create_client

IST = timezone(timedelta(hours=5, minutes=30))
MODEL_DIR = Path(__file__).parent / "models"
MODEL_DIR.mkdir(exist_ok=True)


def get_client():
    url = os.environ.get("SUPABASE_URL", "").strip().strip('"')
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"')
    if not url or not key:
        print("ERROR: set SUPABASE_URL and SUPABASE_KEY env vars")
        raise SystemExit(1)
    return create_client(url, key)


def fetch_labeled(client, limit=50000):
    print("[retrain] Fetching labeled predictions...")
    r = (client.table("predictions")
         .select("*")
         .not_.is_("realized_label", "null")
         .order("id", desc=True)
         .limit(limit)
         .execute())
    return r.data or []


def fetch_features(rows):
    features = ["pcr", "vol_ratio", "straddle", "wall_asym", "mom_5m", "mom_15m"]
    X, y = [], []
    for row in rows:
        feats = row.get("features") or {}
        label = row.get("realized_label")
        if label is None:
            continue
        x = [feats.get(k, 0.0) for k in features]
        if any(not isinstance(v, (int, float)) or np.isnan(v) for v in x):
            continue
        X.append(x)
        y.append(int(label))
    return np.array(X), np.array(y), features


def main():
    client = get_client()
    rows = fetch_labeled(client)
    print(f"[retrain] Got {len(rows)} labeled rows")

    if len(rows) < 200:
        print(f"[retrain] Only {len(rows)} labeled rows. Need 200+. Waiting for more data.")
        return

    X, y, features = fetch_features(rows)
    print(f"[retrain] Training on {len(X)} rows, {len(features)} features")

    # Time-ordered split (avoid lookahead)
    split = int(len(X) * 0.8)
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    # Detect model type from historical labels distribution
    # If labels are 0/1 ? direction; if volatility, we need the volatility model
    # For now, retrain the DIRECTION model
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
    print(f"\n[retrain] Accuracy: {acc:.4f}")
    print(classification_report(y_test, preds, target_names=["DOWN", "UP"]))

    # Save as JSON (cross-version compatible)
    model_path = MODEL_DIR / "xgb_direction.json"
    model.save_model(str(model_path))
    print(f"\n[retrain] Model saved to {model_path}")
    print(f"[retrain] Features: {features}")

    # Save feature list
    (MODEL_DIR / "features.txt").write_text("\n".join(features))
    print(f"[retrain] Done at {datetime.now(IST).strftime('%Y-%m-%d %H:%M IST')}")


if __name__ == "__main__":
    main()

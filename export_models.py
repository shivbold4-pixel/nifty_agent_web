"""
Convert pickle models to XGBoost native JSON format.
Works across Python versions.
"""
import pickle
import xgboost as xgb
from pathlib import Path

MODEL_DIR = Path("models")

for name in ["xgb_direction", "xgb_volatility"]:
    pkl_path = MODEL_DIR / f"{name}.pkl"
    json_path = MODEL_DIR / f"{name}.json"

    if not pkl_path.exists():
        print(f"[skip] {pkl_path} not found")
        continue

    data = pickle.load(open(pkl_path, "rb"))
    model = data["model"]

    # Save in XGBoost's native JSON format
    model.save_model(str(json_path))
    print(f"[OK] {name}: {pkl_path.name} -> {json_path.name}")
    print(f"     Features: {data['features']}")

print()
print("Also saving feature list...")
feats = pickle.load(open(MODEL_DIR / "xgb_volatility.pkl", "rb"))["features"]
with open(MODEL_DIR / "features.txt", "w") as f:
    f.write("\n".join(feats))
print(f"[OK] features.txt saved")

print("\nDONE. Now update volatility_model.py to load JSON.")

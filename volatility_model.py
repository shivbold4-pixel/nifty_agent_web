"""
Model C inference ? loads XGBoost native JSON (cross-version compatible).
"""
import numpy as np
import xgboost as xgb
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "xgb_volatility.json"
FEATURES_PATH = Path(__file__).parent / "models" / "features.txt"

DEFAULT_FEATURES = ["pcr", "vol_ratio", "straddle", "wall_asym", "mom_5m", "mom_15m"]


class VolatilityModel:
    def __init__(self):
        self.model = None
        self.features = DEFAULT_FEATURES
        self._load()

    def _load(self):
        if MODEL_PATH.exists():
            try:
                self.model = xgb.XGBClassifier()
                self.model.load_model(str(MODEL_PATH))
                if FEATURES_PATH.exists():
                    self.features = FEATURES_PATH.read_text().strip().split("\n")
                print(f"[vol_model] Loaded JSON. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
                self.model = None
        else:
            print(f"[vol_model] No file at {MODEL_PATH}")

    def is_ready(self):
        return self.model is not None

    def predict(self, feat_dict):
        if not self.is_ready():
            return "UNKNOWN", 0.0
        try:
            x = np.array([[feat_dict.get(k, 0.0) for k in self.features]])
            proba = self.model.predict_proba(x)[0]
            big_prob = float(proba[1])
            if big_prob >= 0.5:
                return "HIGH", round(big_prob * 100, 1)
            else:
                return "LOW", round((1 - big_prob) * 100, 1)
        except Exception as e:
            print(f"[vol_model] predict error: {e}")
            return "UNKNOWN", 0.0

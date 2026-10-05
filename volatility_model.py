"""
Model C inference ? predicts volatility (BIG vs SMALL move).
"""
import pickle
import numpy as np
from pathlib import Path

MODEL_PATH = Path(__file__).parent / "models" / "xgb_volatility.pkl"


class VolatilityModel:
    def __init__(self):
        self.model = None
        self.features = None
        self._load()

    def _load(self):
        if MODEL_PATH.exists():
            try:
                data = pickle.load(open(MODEL_PATH, "rb"))
                self.model = data["model"]
                self.features = data["features"]
                print(f"[vol_model] Loaded. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
        else:
            print(f"[vol_model] No model at {MODEL_PATH}")

    def is_ready(self):
        return self.model is not None

    def predict(self, feat_dict):
        if not self.is_ready():
            return "UNKNOWN", 0.0
        try:
            x = np.array([[feat_dict.get(k, 0.0) for k in self.features]])
            proba = self.model.predict_proba(x)[0]
            # class 0 = SMALL, class 1 = BIG
            big_prob = float(proba[1])
            if big_prob >= 0.5:
                return "HIGH", round(big_prob * 100, 1)
            else:
                return "LOW", round((1 - big_prob) * 100, 1)
        except Exception as e:
            print(f"[vol_model] predict error: {e}")
            return "UNKNOWN", 0.0

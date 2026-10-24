"""
Model C inference ? loads XGBoost native JSON (cross-version compatible).
"""
import numpy as np
import xgboost as xgb
from pathlib import Path

MODEL_PATH = Path("models/xgb_nifty.pkl")
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
                import pickle
                with open(MODEL_PATH, "rb") as f:
                    loaded_data = pickle.load(f)
                
                # If the .pkl is a dictionary, extract the actual model
                if isinstance(loaded_data, dict):
                    if 'model' in loaded_data:
                        self.model = loaded_data['model']
                    elif 'xgb_model' in loaded_data:
                        self.model = loaded_data['xgb_model']
                    else:
                        print(f"[vol_model] ERROR: Could not find model in dict. Keys: {loaded_data.keys()}")
                        self.model = None
                else:
                    # It's already the model object
                    self.model = loaded_data
                    
                print(f"[vol_model] Loaded Pickle. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
                self.model = None
    def is_ready(self):
        return self.model is not None

    def predict(self, feat_dict):
        if not self.is_ready():
            return "MEDIUM", 0.0
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
            return "MEDIUM", 0.0
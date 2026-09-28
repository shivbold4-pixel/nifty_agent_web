"""Cloud-persistent online learning layer.
Loads model from Supabase on startup. Saves after every N updates.
Retrains from historical labeled data on demand.
"""
import pickle
import numpy as np
from datetime import datetime, timezone, timedelta

from sklearn.linear_model import SGDClassifier
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

from cloud_store import CloudStore

IST = timezone(timedelta(hours=5, minutes=30))

FEATURES = [
    "pcr", "pcr_change", "iv_skew", "wall_asymmetry", "straddle_bps",
    "obi", "weighted_obi", "ofi", "microprice_drift", "queue_imb",
    "cvd_slope", "delta_ratio",
]


class CloudLearner:
    def __init__(self, cloud: CloudStore, min_samples: int = 30):
        self.cloud = cloud
        self.min_samples = min_samples
        self.n_seen = 0
        self._fitted = False
        self.clf = None
        self.scaler = None
        self._updates_since_save = 0
        self._load_from_cloud()

    def _ensure_init(self):
        if self.clf is None:
            self.clf = SGDClassifier(
                loss="log_loss", learning_rate="adaptive",
                eta0=0.05, alpha=1e-4, random_state=7,
            )
            self.scaler = StandardScaler()

    def _vec(self, feats: dict) -> np.ndarray:
        return np.array([feats.get(k, 0.0) for k in FEATURES], dtype=float).reshape(1, -1)

    def update(self, feats: dict, label: int):
        self._ensure_init()
        x = self._vec(feats)
        self.scaler.partial_fit(x)
        try:
            self.clf.partial_fit(self.scaler.transform(x), [label], classes=np.array([0, 1]))
            self._fitted = True
            self.n_seen += 1
            self._updates_since_save += 1
        except Exception as e:
            print(f"[cloud_learner] update error: {e}")
            return

        # Save every 10 updates
        if self._updates_since_save >= 10:
            self._save_to_cloud()
            self._updates_since_save = 0

    def prob_up(self, feats: dict) -> float:
        if not self.is_ready():
            return 0.5
        x = self.scaler.transform(self._vec(feats))
        try:
            return float(self.clf.predict_proba(x)[0, 1])
        except Exception:
            return 0.5

    def is_ready(self) -> bool:
        return self._fitted and self.n_seen >= self.min_samples

    def _save_to_cloud(self):
        if self.clf is None:
            return
        try:
            self.cloud.save_model(self.clf, self.scaler, self.n_seen)
            print(f"[cloud_learner] Model saved. n_samples={self.n_seen}")
        except Exception as e:
            print(f"[cloud_learner] save error: {e}")

    def _load_from_cloud(self):
        try:
            snapshot = self.cloud.load_latest_model()
            if snapshot:
                self.clf = snapshot["clf"]
                self.scaler = snapshot["scaler"]
                self.n_seen = snapshot["n_samples"]
                self._fitted = True
                print(f"[cloud_learner] Model loaded. n_samples={self.n_seen}")
        except Exception as e:
            print(f"[cloud_learner] load error: {e}")

    def force_save(self):
        self._save_to_cloud()

    # ---------------- Batch retrain ----------------
    def retrain_from_history(self) -> dict:
        """
        Pull all labeled predictions from cloud, retrain a fresh model.
        Returns stats dict.
        """
        rows = self.cloud.fetch_labeled(limit=10000)
        if len(rows) < 100:
            return {"status": "insufficient_data", "n": len(rows)}

        X, y = [], []
        for r in rows:
            feats = r.get("features") or {}
            label = r.get("realized_label")
            if label is None:
                continue
            X.append([feats.get(k, 0.0) for k in FEATURES])
            y.append(int(label))

        if len(X) < 100:
            return {"status": "insufficient_clean_data", "n": len(X)}

        X = np.array(X)
        y = np.array(y)

        # Fresh scaler + classifier
        scaler = StandardScaler()
        X_s = scaler.fit_transform(X)

        clf = SGDClassifier(
            loss="log_loss", learning_rate="adaptive",
            eta0=0.03, alpha=1e-4, random_state=7, max_iter=100,
        )
        # Fit on 80% for training
        n_train = int(len(X_s) * 0.8)
        clf.partial_fit(X_s[:n_train], y[:n_train], classes=np.array([0, 1]))

        # Evaluate on held-out 20%
        acc = 0.0
        if len(X_s) - n_train > 10:
            preds = clf.predict(X_s[n_train:])
            acc = float(accuracy_score(y[n_train:], preds))

        # Promote to production model
        self.clf = clf
        self.scaler = scaler
        self.n_seen = len(X)
        self._fitted = True
        self._save_to_cloud()

        return {
            "status": "ok",
            "n_total": len(X),
            "n_train": n_train,
            "accuracy": round(acc, 4),
        }

    # ---------------- Feature attribution ----------------
    def compute_feature_stats(self) -> list:
        rows = self.cloud.fetch_labeled(limit=10000)
        if len(rows) < 50:
            return []
        stats = []
        for feat_name in FEATURES:
            xs, ys = [], []
            for r in rows:
                feats = r.get("features") or {}
                label = r.get("realized_label")
                if label is None:
                    continue
                xs.append(feats.get(feat_name, 0.0))
                ys.append(int(label))
            if len(xs) < 30:
                continue
            xs = np.array(xs)
            ys = np.array(ys)
            # Correlation with label
            if xs.std() > 0:
                corr = float(np.corrcoef(xs, ys)[0, 1])
            else:
                corr = 0.0
            # Hit rate: when feature is positive, does label=1?
            mask = np.abs(xs) > 0.1
            if mask.sum() > 10:
                hit = float(((xs[mask] > 0) == (ys[mask] == 1)).mean())
            else:
                hit = 0.0
            stats.append({
                "feature_name": feat_name,
                "correlation": round(corr, 4),
                "hit_rate": round(hit, 4),
                "n_samples": int(len(xs)),
            })
        return stats

    def save_feature_stats(self):
        stats = self.compute_feature_stats()
        if stats:
            self.cloud.save_feature_stats(stats)
        return stats

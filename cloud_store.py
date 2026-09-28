"""Cloud persistence layer for Nifty Agent.
Stores predictions, model snapshots, and feature stats in Supabase.
"""
import os
import pickle
import base64
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from supabase import create_client, Client

IST = timezone(timedelta(hours=5, minutes=30))


def get_supabase_client(url: str, key: str) -> Client:
    return create_client(url, key)


class CloudStore:
    def __init__(self, url: str, key: str):
        self.client = get_supabase_client(url, key)

    # ---------------- Predictions ----------------
    def save_prediction(self, pred: dict, features: dict) -> bool:
        try:
            row = {
                "pred_ts": float(pred.get("ts", 0)),
                "ts_ist": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "spot": float(pred.get("spot", 0)),
                "direction": str(pred.get("direction", "FLAT")),
                "score": float(pred.get("score", 0)),
                "confidence": float(pred.get("confidence", 0)),
                "regime": str(pred.get("regime", "NORMAL")),
                "action": str(pred.get("action", "STAND ASIDE")),
                "features": json.loads(json.dumps(features, default=str)),
            }
            self.client.table("predictions").insert(row).execute()
            return True
        except Exception as e:
            print(f"[cloud_store] save_prediction error: {e}")
            return False

    def update_outcome(self, pred_ts: float, outcome_bps: float, label: int) -> bool:
        try:
            self.client.table("predictions").update({
                "outcome_bps": float(outcome_bps),
                "realized_label": int(label),
            }).eq("pred_ts", float(pred_ts)).execute()
            return True
        except Exception as e:
            print(f"[cloud_store] update_outcome error: {e}")
            return False

    def fetch_recent_predictions(self, limit: int = 5000) -> List[dict]:
        try:
            resp = (self.client.table("predictions")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute())
            return resp.data or []
        except Exception as e:
            print(f"[cloud_store] fetch_recent_predictions error: {e}")
            return []

    def fetch_labeled(self, limit: int = 10000) -> List[dict]:
        try:
            resp = (self.client.table("predictions")
                    .select("*")
                    .not_.is_("realized_label", "null")
                    .order("created_at", desc=True)
                    .limit(limit)
                    .execute())
            return resp.data or []
        except Exception as e:
            print(f"[cloud_store] fetch_labeled error: {e}")
            return []

    def count_predictions(self) -> int:
        try:
            resp = self.client.table("predictions").select("id", count="exact").execute()
            return resp.count or 0
        except Exception:
            return 0

    # ---------------- Model snapshots ----------------
    def save_model(self, clf, scaler, n_samples: int, accuracy: float = 0.0) -> bool:
        try:
            clf_bytes = pickle.dumps(clf)
            scaler_bytes = pickle.dumps(scaler)
            row = {
                "model_blob": base64.b64encode(clf_bytes).decode("ascii"),
                "scaler_blob": base64.b64encode(scaler_bytes).decode("ascii"),
                "n_samples": int(n_samples),
                "accuracy": float(accuracy),
            }
            self.client.table("model_snapshots").insert(row).execute()
            # Keep only last 10 snapshots
            self._prune_snapshots()
            return True
        except Exception as e:
            print(f"[cloud_store] save_model error: {e}")
            return False

    def load_latest_model(self):
        try:
            resp = (self.client.table("model_snapshots")
                    .select("*")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute())
            if not resp.data:
                return None
            row = resp.data[0]
            clf = pickle.loads(base64.b64decode(row["model_blob"]))
            scaler = pickle.loads(base64.b64decode(row["scaler_blob"]))
            return {
                "clf": clf,
                "scaler": scaler,
                "n_samples": row["n_samples"],
                "accuracy": row.get("accuracy", 0.0),
            }
        except Exception as e:
            print(f"[cloud_store] load_latest_model error: {e}")
            return None

    def _prune_snapshots(self):
        try:
            resp = (self.client.table("model_snapshots")
                    .select("id")
                    .order("created_at", desc=True)
                    .execute())
            if resp.data and len(resp.data) > 10:
                old_ids = [r["id"] for r in resp.data[10:]]
                for oid in old_ids:
                    self.client.table("model_snapshots").delete().eq("id", oid).execute()
        except Exception:
            pass

    # ---------------- Feature stats ----------------
    def save_feature_stats(self, stats: List[Dict]) -> bool:
        try:
            if not stats:
                return False
            self.client.table("feature_stats").insert(stats).execute()
            return True
        except Exception as e:
            print(f"[cloud_store] save_feature_stats error: {e}")
            return False

"""Nifty Agent with cloud-persistent learning."""
import time
import numpy as np
import pandas as pd
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import yaml

from cloud_store import CloudStore
from cloud_learner import CloudLearner
from volatility_model import VolatilityModel
from regime_detector import RegimeDetector
from risk_manager import RiskManager

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path=CONFIG_PATH):
    with open(path) as f:
        return yaml.safe_load(f)


@dataclass
class Prediction:
    ts: float
    spot: float
    direction: str
    score: float
    confidence: float
    expected_points: float
    regime: str
    size_mult: float
    action: str
    stop_loss: float
    take_profit: float
    volatility: str
    volatility_conf: float
    can_trade: bool
    risk_reason: str
    contributions: dict
    features: dict


def option_features(df, spot=None):
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    alias = {
        "call_oi": ["ce_oi"], "put_oi": ["pe_oi"],
        "call_oi_change": ["ce_oi_change"], "put_oi_change": ["pe_oi_change"],
        "call_ltp": ["ce_ltp"], "put_ltp": ["pe_ltp"],
        "call_iv": ["ce_iv"], "put_iv": ["pe_iv"],
    }
    for tgt, opts in alias.items():
        if tgt not in df.columns:
            for o in opts:
                if o in df.columns:
                    df[tgt] = df[o]; break
    for c in df.columns:
        if df[c].dtype == object:
            df[c] = pd.to_numeric(df[c].astype(str).str.replace(",", ""), errors="coerce")
    df = df.dropna(subset=["strike"]).sort_values("strike").reset_index(drop=True)
    if spot is None:
        diff = (df.call_ltp - df.put_ltp).abs()
        spot = float(df.loc[diff.idxmin(), "strike"])
    total_call = max(df.call_oi.sum(), 1)
    total_put = max(df.put_oi.sum(), 1)
    pcr = total_put / total_call
    d_call = df.call_oi_change.sum() if "call_oi_change" in df else 0
    d_put = df.put_oi_change.sum() if "put_oi_change" in df else 0
    pcr_change = (d_put / d_call) if d_call else 1.0
    atm_idx = (df.strike - spot).abs().idxmin()
    atm_row = df.loc[atm_idx]
    atm = float(atm_row.strike)
    straddle = float(atm_row.call_ltp + atm_row.put_ltp)
    iv_skew = float(atm_row.put_iv - atm_row.call_iv) if "call_iv" in df else 0.0
    call_wall = float(df.nlargest(min(3, len(df)), "call_oi").strike.mean())
    put_wall = float(df.nlargest(min(3, len(df)), "put_oi").strike.mean())
    wall_asym = (put_wall - call_wall) / max(spot, 1)
    return {
        "spot": spot, "atm": atm, "pcr": pcr, "pcr_change": pcr_change,
        "iv_skew": iv_skew, "wall_asymmetry": wall_asym,
        "straddle_bps": straddle / max(spot, 1) * 1e4,
        "call_wall": call_wall, "put_wall": put_wall, "straddle": straddle,
    }


class CVDEngine:
    def __init__(self):
        self.trades = deque(maxlen=5000)
        self.cvd = 0.0
        self._prev_px = 0.0

    def on_tick(self, px, qty, bid, ask, ts):
        if ask and px >= ask: side = 1
        elif bid and px <= bid: side = -1
        elif self._prev_px:
            side = 1 if px > self._prev_px else (-1 if px < self._prev_px else 0)
        else: side = 0
        self.trades.append({"ts": ts, "qty": qty, "side": side})
        self.cvd += side * qty
        self._prev_px = px
        cutoff = ts - 60
        buy = sum(t["qty"] for t in self.trades if t["ts"] >= cutoff and t["side"] == 1)
        sell = sum(t["qty"] for t in self.trades if t["ts"] >= cutoff and t["side"] == -1)
        delta = buy - sell
        tot = buy + sell + 1e-9
        return {"cvd_slope": delta / 60.0, "delta_ratio": delta / tot}


def classify_regime(vix, cfg):
    r = cfg["regime"]
    if vix < r["vix_calm_max"]:
        return "CALM", r["size_calm"], "Trend mode."
    if vix < r["vix_panic_min"]:
        return "NORMAL", r["size_normal"], "Selective."
    return "PANIC", r["size_panic"], "Cut exposure."


OPTION_WEIGHTS = {"pcr": 0.35, "pcr_change": 0.20, "iv_skew": -0.20,
                  "wall_asymmetry": 0.20, "straddle_bps": -0.05}
OPTION_CENTERS = {"pcr": 1.0, "pcr_change": 1.0, "iv_skew": 0.0,
                  "wall_asymmetry": 0.0, "straddle_bps": 80.0}
OPTION_SCALES = {"pcr": 0.30, "pcr_change": 0.30, "iv_skew": 5.0,
                 "wall_asymmetry": 0.02, "straddle_bps": 100.0}
DEPTH_WEIGHTS = {"ofi": 0.40, "microprice_drift": 0.20, "weighted_obi": 0.15,
                 "obi": 0.15, "queue_imb": 0.10}
DEPTH_SCALES = {"ofi": 250.0, "microprice_drift": 3.0, "weighted_obi": 1.0,
                "obi": 1.0, "queue_imb": 1.0}
CVD_WEIGHTS = {"cvd_slope": 0.60, "delta_ratio": 0.40}
CVD_SCALES = {"cvd_slope": 50.0, "delta_ratio": 1.0}


def _score(feats, weights, scales, centers=None):
    centers = centers or {}
    s = 0.0
    for k, w in weights.items():
        v = feats.get(k, 0.0) - centers.get(k, 0.0)
        s += w * float(np.tanh(v / scales.get(k, 1.0)))
    return float(np.clip(s, -1, 1))


class NiftyAgent:
    def __init__(self, config_path=CONFIG_PATH, supabase_url=None, supabase_key=None):
        self.cfg = load_config(config_path)

        # Cloud persistence
        self.cloud = None
        self.learner = None
        if supabase_url and supabase_key:
            try:
                self.cloud = CloudStore(supabase_url, supabase_key)
                self.learner = CloudLearner(
                    self.cloud,
                    min_samples=self.cfg["agent"].get("online_min_samples", 30),
                )
                print(f"[agent] Cloud connected. History: {self.cloud.count_predictions()} predictions")
            except Exception as e:
                print(f"[agent] Cloud init failed: {e}")

        self.depth_hist = deque(maxlen=120)
        self.cvd = CVDEngine()
        self.last_option_feats = None
        self.last_option_ts = 0.0
        self.last_depth_feats = {"obi": 0.0, "weighted_obi": 0.0, "ofi": 0.0,
                                 "microprice_drift": 0.0, "queue_imb": 0.0}
        self.last_cvd_feats = {"cvd_slope": 0.0, "delta_ratio": 0.0}
        self.vix = 15.0
        self.recent_spots = []
        self._pending = None
        self.vol_model = VolatilityModel()
        self.risk = RiskManager()

    def on_option_chain(self, df, spot=None, vix=None):
        feats = option_features(df, spot=spot)
        self.last_option_feats = feats
        self.last_option_ts = time.time()
        if vix is not None:
            self.vix = vix

    def predict(self):
        if self.last_option_feats is None:
            raise RuntimeError("Call on_option_chain() before predict()")

        # Sanitize NaN values in features
        def _sanitize(d):
            return {k: (0.0 if (v is None or (isinstance(v, float) and np.isnan(v))) else v)
                    for k, v in d.items()}
        self.last_option_feats = _sanitize(self.last_option_feats)
        self.last_depth_feats = _sanitize(self.last_depth_feats)
        self.last_cvd_feats = _sanitize(self.last_cvd_feats)
        opt_score = _score(self.last_option_feats, OPTION_WEIGHTS, OPTION_SCALES, OPTION_CENTERS)
        depth_score = _score(self.last_depth_feats, DEPTH_WEIGHTS, DEPTH_SCALES)
        cvd_score = _score(self.last_cvd_feats, CVD_WEIGHTS, CVD_SCALES)

        has_depth = any(v != 0.0 for v in self.last_depth_feats.values())
        has_cvd = any(v != 0.0 for v in self.last_cvd_feats.values())

        wd = self.cfg["agent"]["weight_depth"] if has_depth else 0.0

        # ==========================================
        # UPGRADE 5: Volume Profile scoring
        # ==========================================
        vp_feats = self.last_option_feats.get("_vp_feats", {})
        gex_feats = self.last_option_feats.get("_gex_feats", {})
        vp_score = 0.0
        if vp_feats and vp_feats.get("vah") is not None:
            try:
                vp_pos = float(vp_feats.get("vp_position", 0.5))
                vp_pos_centered = float(np.clip((vp_pos - 0.5) * 2, -1, 1))
                poc_dist = float(vp_feats.get("vp_distance_poc", 0.0))
                poc_signal = -float(np.tanh(poc_dist / 0.01))
                vp_score = float(np.clip(0.6 * vp_pos_centered + 0.4 * poc_signal, -1, 1))
            except Exception as _e:
                print(f"[agent] vp_score error: {_e}")
                vp_score = 0.0
        wc = self.cfg["agent"]["weight_cvd"] if has_cvd else 0.0
        wo = self.cfg["agent"]["weight_options"]
        wvp = 0.15  # Volume Profile weight
        total_w = wd + wc + wo + wvp
        blended = (wd * depth_score + wc * cvd_score + wo * opt_score + wvp * vp_score) / total_w

        regime, size_mult, note = classify_regime(self.vix, self.cfg)
        if regime == "PANIC":
            blended *= 0.5

        combined_feats = {**self.last_option_feats, **self.last_depth_feats, **self.last_cvd_feats}

        ml_prob = 0.5
        if self.learner is not None:
            ml_prob = self.learner.prob_up(combined_feats)
            if self.learner.is_ready():
                blended = 0.70 * blended + 0.30 * (ml_prob - 0.5) * 2

        # ============================================================
        # MULTI-TIMEFRAME MOMENTUM ENGINE
        # Reads price across 5m / 15m / 30m windows.
        # Overrides option signal when price moves decisively.
        # ============================================================
        _spot_now = self.last_option_feats["spot"]
        _ts_now = time.time()
        self.recent_spots.append((_ts_now, _spot_now))
        if len(self.recent_spots) > 10:
            self.recent_spots = self.recent_spots[-10:]

        def _pct(a, b):
            return (a - b) / b if b and b > 0 else 0.0

        mom_5m = mom_15m = mom_30m = 0.0
        if len(self.recent_spots) >= 2:
            mom_5m = _pct(_spot_now, self.recent_spots[-2][1])
        if len(self.recent_spots) >= 4:
            mom_15m = _pct(_spot_now, self.recent_spots[-4][1])
        if len(self.recent_spots) >= 7:
            mom_30m = _pct(_spot_now, self.recent_spots[-7][1])

        def _strength(pct):
            ap = abs(pct)
            if ap >= 0.0040: return 0.50
            if ap >= 0.0030: return 0.40
            if ap >= 0.0020: return 0.30
            if ap >= 0.0010: return 0.18
            if ap >= 0.0005: return 0.08
            return 0.0

        momentum_override = 0.0
        if mom_15m < 0:
            momentum_override = -_strength(mom_15m)
        elif mom_15m > 0:
            momentum_override = _strength(mom_15m)

        # Agreement bonus: 5m and 15m agree
        if mom_5m * mom_15m > 0 and abs(mom_5m) > 0.0010:
            momentum_override *= 1.20

        # Trend bonus: 3+ consecutive same-direction moves
        _consecutive = 0
        _direction = 0
        if len(self.recent_spots) >= 4:
            for _i in range(len(self.recent_spots) - 1, 1, -1):
                _d = self.recent_spots[_i][1] - self.recent_spots[_i - 1][1]
                _sgn = 1 if _d > 0 else (-1 if _d < 0 else 0)
                if _sgn == 0:
                    break
                if _direction == 0:
                    _direction = _sgn
                    _consecutive = 1
                elif _sgn == _direction:
                    _consecutive += 1
                else:
                    break

        if _consecutive >= 3:
            momentum_override *= 1.15

        # Cap at ?0.55
        momentum_override = max(-0.55, min(0.55, momentum_override))

        blended += momentum_override

        # ============================================================
        # TREND PERSISTENCE (catches slow sustained trends)
        # ============================================================
        trend_score = 0.0
        if len(self.recent_spots) >= 6:
            last6 = [s[1] for s in self.recent_spots[-6:]]
            moves = [last6[i] - last6[i-1] for i in range(1, 6)]
            ups = sum(1 for m in moves if m > 0)
            downs = sum(1 for m in moves if m < 0)
            if ups >= 5:
                trend_score = 0.25
            elif ups == 4:
                trend_score = 0.12
            elif downs >= 5:
                trend_score = -0.25
            elif downs == 4:
                trend_score = -0.12
        blended += trend_score

        # ============================================================
        # REVERSAL OVERRIDE
        # When Nifty moves sharply against the options layer's direction,
        # trust price over positioning. Forces a signal on trend reversals.
        # ============================================================
        # 15-min override (sharp moves) or 30-min override (slower trends)
        if (mom_15m >= 0.0015 or mom_30m >= 0.0020) and opt_score < -0.15:
            blended = max(blended, 0.40)
        elif (mom_15m <= -0.0015 or mom_30m <= -0.0020) and opt_score > 0.15:
            blended = min(blended, -0.40)

        # ==========================================
        # UPGRADE 5: GEX regime confidence modifier
        # ==========================================
        gex_norm = 0.0
        gex_regime_label = "NEUTRAL"
        if gex_feats:
            try:
                gex_norm = float(gex_feats.get("gex_normalized", 0.0))
                gex_regime_label = gex_feats.get("gex_regime", "NEUTRAL")
            except Exception:
                gex_norm = 0.0

        if gex_norm < -0.2:
            blended *= 1.15  # trending regime ? amplify
        elif gex_norm > 0.2:
            blended *= 0.85  # mean-reverting regime ? dampen

        if np.isnan(blended):
            blended = 0.0
        blended = float(np.clip(blended, -1, 1))

        th = self.cfg["agent"]["direction_threshold"]
        if blended > th: direction = "BULLISH"
        elif blended < -th: direction = "BEARISH"
        else: direction = "FLAT"

        confidence = round(min(abs(blended) * 100, 100), 1)
        spot = self.last_option_feats["spot"]
        straddle = self.last_option_feats.get("straddle", 50)
        exp_pts = round(abs(blended) * max(straddle * 0.15, 5.0), 1)

        atr_proxy = max(straddle * 0.15, 8.0)
        rk = self.cfg["risk"]
        if direction == "BULLISH":
            stop = round(spot - atr_proxy * rk["stop_atr_mult"], 1)
            target = round(spot + atr_proxy * rk["target_atr_mult"], 1)
        elif direction == "BEARISH":
            stop = round(spot + atr_proxy * rk["stop_atr_mult"], 1)
            target = round(spot - atr_proxy * rk["target_atr_mult"], 1)
        else:
            stop = target = 0.0

        if direction == "FLAT" or confidence < self.cfg["agent"]["min_confidence"]:
            action = "STAND ASIDE"
        elif regime == "PANIC":
            action = "STAND ASIDE (panic regime)"
        else:
            action = "BUY NIFTY FUT" if direction == "BULLISH" else "SELL NIFTY FUT"

        # ==================================================
        # REGIME DETECTION
        # ==================================================
        try:
            self.regime_detector.update(_spot_now, self.vix)
            regime_info = self.regime_detector.status()
            regime_size = self.regime_detector.size_multiplier()
        except Exception as _e:
            print(f"[agent] regime error: {_e}")
            regime_info = {"regime": "UNKNOWN", "confidence": 0.0, "size_mult": 0.5}
            regime_size = 0.5

        # ==================================================
        # VOLATILITY MODEL C inference
        # ==================================================
        vol_label = "UNKNOWN"
        vol_conf = 0.0
        try:
            vol_label, vol_conf = self.vol_model.predict(combined_feats)
        except Exception as _e:
            print(f"[agent] vol error: {_e}")

        # ==================================================
        # RISK MANAGEMENT
        # ==================================================
        can_trade, risk_reason = self.risk.check_can_trade()

        # Adjust size by volatility + risk
        base_mult = size_mult
        if vol_label == "HIGH" and vol_conf >= 60:
            base_mult *= 1.3
            action_note = " (High vol - size up)"
        elif vol_label == "LOW" and vol_conf >= 60:
            base_mult *= 0.7
            action_note = " (Low vol - size down)"
        else:
            action_note = ""

        base_mult *= regime_size
        base_mult = self.risk.adjust_size_mult(base_mult)

        # Override action if risk says stop
        if not can_trade:
            action = f"HALTED ? {risk_reason}"
        else:
            action = action + action_note

        pred = Prediction(
            ts=time.time(), spot=spot, direction=direction,
            score=round(blended, 3), confidence=confidence,
            expected_points=exp_pts, regime=regime, size_mult=size_mult,
            action=action, stop_loss=stop, take_profit=target,
            volatility=vol_label,
            volatility_conf=vol_conf,
            can_trade=can_trade,
            risk_reason=risk_reason,
            contributions={"options": round(opt_score, 3), "depth": round(depth_score, 3),
                           "cvd": round(cvd_score, 3), "vp_score": round(vp_score, 3),
                           "gex_norm": round(gex_norm, 3),
                           "momentum": round(momentum_override, 3),
                           "trend": round(trend_score, 3),
                           "regime_conf": round(regime_info.get("confidence", 0), 1),
                           "ml_prob": round(ml_prob, 3),
                           "vol_conf": round(vol_conf, 1),
                           "regime": regime_info.get("regime", "UNKNOWN")},
            features=combined_feats,
        )

        # Save prediction to cloud
        if self.cloud is not None:
            try:
                self.cloud.save_prediction({
                    "ts": pred.ts, "spot": pred.spot, "direction": pred.direction,
                    "score": pred.score, "confidence": pred.confidence,
                    "regime": pred.regime, "action": pred.action,
                }, combined_feats)
            except Exception as e:
                print(f"[agent] cloud save failed: {e}")

        self._pending = {"ts": pred.ts, "spot": spot, "feats": combined_feats}
        return pred

    def label_previous(self, next_spot):
        if not self._pending:
            return
        realized_bps = (next_spot - self._pending["spot"]) / self._pending["spot"] * 1e4
        label = 1 if realized_bps > 0 else 0

        # Update local online model
        if self.learner is not None:
            self.learner.update(self._pending["feats"], label)

        # Update cloud outcome
        if self.cloud is not None:
            try:
                self.cloud.update_outcome(self._pending["ts"], realized_bps, label)
            except Exception as e:
                print(f"[agent] outcome update failed: {e}")

        self._pending = None

    def force_save_model(self):
        if self.learner is not None:
            self.learner.force_save()

    def retrain(self):
        if self.learner is not None:
            return self.learner.retrain_from_history()
        return {"status": "no_learner"}

"""
Trend Maturity Filter v3 ? distinguishes healthy trends from parabolic spikes.

Key insight:
- Healthy trend: small moves (5-15 pts), pullbacks every 30-60 min, VWAP rising
- Parabolic spike: large moves (30-60 pts), no pullbacks, VWAP lags
- Exhaustion: fresh extreme + RSI oversold/overbought + no pullbacks
"""
import numpy as np
from collections import deque
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


class TrendMaturityFilter:
    def __init__(self, history_size: int = 30):
        self.prices = deque(maxlen=history_size)
        self.timestamps = deque(maxlen=history_size)

    def update(self, spot: float):
        self.prices.append(spot)
        self.timestamps.append(datetime.now(IST))

    def _rsi(self, arr: np.ndarray, period: int = 14) -> float:
        if len(arr) < period + 1:
            return 50.0
        deltas = np.diff(arr[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        ag = float(np.mean(gains))
        al = float(np.mean(losses))
        if al == 0:
            return 100.0
        return 100 - (100 / (1 + ag/al))

    def compute(self) -> dict:
        # Fallback defaults for NSE timeout
        trend_up_healthy = False
        trend_down_healthy = False
        if len(self.prices) < 12:
            return self._empty("WARMUP")

        arr = np.array(self.prices)
        spot = float(arr[-1])

        # ---- MOVE SIZE ANALYSIS ----
        moves = np.abs(np.diff(arr))
        recent_moves = moves[-5:] if len(moves) >= 5 else moves
        normal_moves = moves[:-5] if len(moves) > 5 else moves
        recent_avg = float(np.mean(recent_moves)) if len(recent_moves) else 0
        normal_avg = float(np.mean(normal_moves)) if len(normal_moves) else recent_avg
        move_ratio = recent_avg / normal_avg if normal_avg > 0.01 else 1.0

        # ---- PULLBACK ANALYSIS ----
        deltas = np.diff(arr[-12:])
        direction_changes = 0
        prev_sign = 0
        for d in deltas:
            sgn = 1 if d > 0.5 else (-1 if d < -0.5 else 0)
            if sgn != 0 and prev_sign != 0 and sgn != prev_sign:
                direction_changes += 1
            if sgn != 0:
                prev_sign = sgn

        # ---- VWAP AND SLOPE ----
        weights = np.arange(1, len(arr) + 1)
        vwap = float(np.average(arr, weights=weights))
        vwap_distance = (spot - vwap) / vwap if vwap > 0 else 0.0

        # VWAP slope: compare recent half vs older half
        if len(arr) >= 10:
            early_vwap = float(np.mean(arr[:-5]))
            late_vwap = float(np.mean(arr[-5:]))
            vwap_slope = (late_vwap - early_vwap) / early_vwap if early_vwap > 0 else 0.0
        else:
            vwap_slope = 0.0

        # ---- RSI ----
        rsi = self._rsi(arr)

        # ---- OVERALL TREND DIRECTION ----
        overall_move = (spot - arr[0]) / arr[0] if arr[0] > 0 else 0.0
        abs_move = abs(overall_move)

        # ============================================================
        # CLASSIFICATION
        # ============================================================

        # Rule 1: PARABOLIC SPIKE ? dangerous, suppress hard
        # Large moves + few pullbacks + price far from VWAP
        is_parabolic = (
            move_ratio >= 2.0
            and direction_changes <= 1
            and abs(vwap_distance) > 0.0075
        )

        # Rule 2: EXHAUSTION ? fresh extreme + RSI extreme + no pullback
        # Price at new high/low AND momentum extreme
        recent_high = float(np.max(arr[-5:]))
        recent_low = float(np.min(arr[-5:]))
        prior_high = float(np.max(arr[-12:-5])) if len(arr) >= 12 else recent_high
        prior_low = float(np.min(arr[-12:-5])) if len(arr) >= 12 else recent_low

        new_high = recent_high >= prior_high * 0.999
        new_low = recent_low <= prior_low * 1.001

        is_exhausted_up = new_high and rsi > 72 and direction_changes <= 1
        is_exhausted_down = new_low and rsi < 28 and direction_changes <= 1
        is_exhausted = is_exhausted_up or is_exhausted_down

        # Rule 3: HEALTHY TREND ? gradual, pullbacks, VWAP trending
        # This is the case we MISSED today ? needs to be TRADED
        is_healthy_trend = (
            move_ratio < 1.7
            and direction_changes >= 2
            and abs(vwap_slope) > 0.0003
            and abs_move > 0.0015
        )

        # Rule 4: CHOPPY ? no clear direction
        total_up = sum(1 for d in deltas if d > 0.5)
        total_down = sum(1 for d in deltas if d < -0.5)
        is_choppy = (
            not is_healthy_trend
            and not is_parabolic
            and not is_exhausted
            and abs_move < 0.002
        )

        # ========================================
        # SUPPRESSION FACTOR (v4 - VWAP slope aware)
        # ========================================
        if is_parabolic:
            suppression = 0.25
            state = 'PARABOLIC'
        elif is_exhausted and not (trend_up_healthy or trend_down_healthy):
            suppression = 0.35
            state = 'EXHAUSTED'
        elif is_exhausted and (trend_up_healthy or trend_down_healthy):
            # Trend is exhausted BUT VWAP is trending -> softer suppression
            suppression = 0.75
            state = 'TRENDING_EXTENDED'
        elif is_healthy_trend:
            suppression = 1.0
            state = 'HEALTHY_TREND'
        elif trend_up_healthy or trend_down_healthy:
            # VWAP confirms trend but TMF didn't flag as healthy
            suppression = 0.95
            state = 'TRENDING'
        elif is_choppy:
            suppression = 0.6
            state = 'CHOPPY'
        else:
            suppression = 0.85
            state = 'NEUTRAL'


        return {
            "state": state,
            "suppression": round(suppression, 3),
            "move_ratio": round(move_ratio, 3),
            "direction_changes": direction_changes,
            "vwap_distance_pct": round(vwap_distance * 100, 3),
            "vwap_slope_pct": round(vwap_slope * 100, 4),
            "rsi": round(rsi, 1),
            "overall_move_pct": round(overall_move * 100, 3),
            "is_parabolic": is_parabolic,
            "is_exhausted": is_exhausted,
            "is_healthy_trend": is_healthy_trend,
            "is_choppy": is_choppy,
        }

    def _empty(self, state: str) -> dict:
        return {
            "state": state,
            "suppression": 1.0,
            "move_ratio": 1.0,
            "direction_changes": 0,
            "vwap_distance_pct": 0.0,
            "vwap_slope_pct": 0.0,
            "rsi": 50.0,
            "overall_move_pct": 0.0,
            "is_parabolic": False,
            "is_exhausted": False,
            "is_healthy_trend": False,
            "is_choppy": False,
        }
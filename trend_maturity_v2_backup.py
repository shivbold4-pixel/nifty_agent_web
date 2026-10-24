"""
Trend Maturity Filter v2 ? Multi-signal exhaustion detector.
"""
import numpy as np
from collections import deque
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


class TrendMaturityFilter:
    def __init__(self, history_size: int = 30):
        self.prices = deque(maxlen=history_size)
        self.timestamps = deque(maxlen=history_size)
        self.highs = deque(maxlen=history_size)
        self.lows = deque(maxlen=history_size)

    def update(self, spot: float, high: float = None, low: float = None):
        self.prices.append(spot)
        self.timestamps.append(datetime.now(IST))
        self.highs.append(high if high is not None else spot)
        self.lows.append(low if low is not None else spot)

    def _rsi(self, arr: np.ndarray, period: int = 14) -> float:
        if len(arr) < period + 1:
            return 50.0
        deltas = np.diff(arr[-(period+1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _vwap(self) -> float:
        if not self.prices:
            return 0.0
        arr = np.array(self.prices)
        weights = np.arange(1, len(arr) + 1)
        return float(np.average(arr, weights=weights))

    def compute(self) -> dict:
        if len(self.prices) < 10:
            return self._empty_result("INSUFFICIENT_DATA")

        arr = np.array(self.prices)
        current = float(arr[-1])

        # SIGNAL 1: Distance from VWAP
        vwap = self._vwap()
        distance_pct = (current - vwap) / vwap if vwap > 0 else 0.0
        abs_distance = abs(distance_pct)

        if abs_distance >= 0.015: s1 = 1.0
        elif abs_distance >= 0.010: s1 = 0.7
        elif abs_distance >= 0.006: s1 = 0.4
        elif abs_distance >= 0.003: s1 = 0.15
        else: s1 = 0.0

        # SIGNAL 2: Consecutive same-direction moves
        if len(arr) >= 3:
            deltas = np.diff(arr)
            consecutive = 0
            direction = 0
            for d in reversed(deltas):
                sgn = 1 if d > 0 else (-1 if d < 0 else 0)
                if sgn == 0:
                    break
                if direction == 0:
                    direction = sgn
                    consecutive = 1
                elif sgn == direction:
                    consecutive += 1
                else:
                    break
        else:
            consecutive = 0
            direction = 0

        if consecutive >= 9: s2 = 1.0
        elif consecutive >= 7: s2 = 0.7
        elif consecutive >= 5: s2 = 0.4
        elif consecutive >= 3: s2 = 0.15
        else: s2 = 0.0

        # SIGNAL 3: RSI extreme + new low/high
        rsi = self._rsi(arr)
        recent_low = float(np.min(arr[-5:])) if len(arr) >= 5 else current
        recent_high = float(np.max(arr[-5:])) if len(arr) >= 5 else current
        prior_low = float(np.min(arr[-10:-5])) if len(arr) >= 10 else recent_low
        prior_high = float(np.max(arr[-10:-5])) if len(arr) >= 10 else recent_high

        bullish_exhaust = 0.0
        if rsi < 25 and recent_low <= prior_low * 1.001: bullish_exhaust = 1.0
        elif rsi < 30 and recent_low <= prior_low * 1.002: bullish_exhaust = 0.7
        elif rsi < 35: bullish_exhaust = 0.3

        bearish_exhaust = 0.0
        if rsi > 75 and recent_high >= prior_high * 0.999: bearish_exhaust = 1.0
        elif rsi > 70 and recent_high >= prior_high * 0.998: bearish_exhaust = 0.7
        elif rsi > 65: bearish_exhaust = 0.3

        s3 = max(bullish_exhaust, bearish_exhaust)

        # SIGNAL 4: Rate of Change deceleration
        s4 = 0.0
        if len(arr) >= 10:
            recent_moves = np.abs(np.diff(arr[-5:]))
            prior_moves = np.abs(np.diff(arr[-10:-5]))
            recent_avg = float(np.mean(recent_moves))
            prior_avg = float(np.mean(prior_moves))
            if prior_avg > 0:
                ratio = recent_avg / prior_avg
                if ratio < 0.3: s4 = 1.0
                elif ratio < 0.5: s4 = 0.7
                elif ratio < 0.7: s4 = 0.4
                elif ratio < 0.85: s4 = 0.15

        # COMPOSITE
        exhaustion_score = 0.35 * s1 + 0.25 * s2 + 0.25 * s3 + 0.15 * s4
        exhaustion_score = float(np.clip(exhaustion_score, 0, 1))

        suppression = 1.0 - (exhaustion_score * 0.75)
        suppression = float(np.clip(suppression, 0.25, 1.0))

        direction_hint = 0
        if bullish_exhaust >= 0.5: direction_hint = 1
        elif bearish_exhaust >= 0.5: direction_hint = -1

        if exhaustion_score >= 0.75: state = "EXHAUSTED"
        elif exhaustion_score >= 0.5: state = "MATURE"
        elif exhaustion_score >= 0.25: state = "DEVELOPING"
        else: state = "FRESH"

        return {
            "exhaustion_score": round(exhaustion_score, 3),
            "suppression": round(suppression, 3),
            "direction_hint": direction_hint,
            "state": state,
            "signals": {
                "vwap_distance": round(s1, 3),
                "consecutive": round(s2, 3),
                "rsi_extreme": round(s3, 3),
                "deceleration": round(s4, 3),
            },
            "metrics": {
                "vwap": round(vwap, 2),
                "distance_pct": round(distance_pct * 100, 3),
                "rsi": round(rsi, 1),
                "consecutive": consecutive,
                "direction": direction,
            },
        }

    def _empty_result(self, state: str) -> dict:
        return {
            "exhaustion_score": 0.0,
            "suppression": 1.0,
            "direction_hint": 0,
            "state": state,
            "signals": {},
            "metrics": {},
        }

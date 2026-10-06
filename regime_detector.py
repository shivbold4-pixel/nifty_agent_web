"""
Market regime detection ? rule-based.
Uses Nifty momentum + volatility to classify current state.
"""
import numpy as np
from datetime import timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


class RegimeDetector:
    """Classifies the current market regime from recent price action."""

    def __init__(self, history_size: int = 12):
        self.history_size = history_size
        self.spots = []   # list of (ts, price)
        self.regime = "UNKNOWN"
        self.confidence = 0.0

    def update(self, spot: float, vix: float = 15.0):
        """Call on every fetch. Updates regime classification."""
        self.spots.append(spot)
        if len(self.spots) > self.history_size:
            self.spots = self.spots[-self.history_size:]

        if len(self.spots) < 4:
            self.regime = "WARMUP"
            self.confidence = 0.0
            return

        arr = np.array(self.spots)

        # Momentum over the visible window
        total_move = (arr[-1] - arr[0]) / arr[0]
        # Volatility ? std of returns
        returns = np.diff(arr) / arr[:-1]
        volatility = float(np.std(returns)) * 100
        # Direction consistency
        ups = int((np.diff(arr) > 0).sum())
        downs = int((np.diff(arr) < 0).sum())
        total = ups + downs
        consistency = max(ups, downs) / total if total > 0 else 0

        # Classify
        if vix > 22:
            self.regime = "CRISIS"
            self.confidence = min((vix - 22) * 5, 100)
        elif abs(total_move) >= 0.005 and consistency >= 0.65:
            # Strong trend: >0.5% total move, 65%+ windows same direction
            self.regime = "TRENDING_UP" if total_move > 0 else "TRENDING_DOWN"
            self.confidence = min(abs(total_move) * 10000, 100)
        elif volatility >= 0.15:
            self.regime = "VOLATILE"
            self.confidence = min(volatility * 300, 100)
        else:
            self.regime = "CHOPPY"
            self.confidence = min(100 - (volatility * 300), 100)

    def size_multiplier(self) -> float:
        return {
            "TRENDING_UP": 1.0,
            "TRENDING_DOWN": 1.0,
            "CHOPPY": 0.5,
            "VOLATILE": 0.6,
            "CRISIS": 0.2,
            "WARMUP": 0.5,
            "UNKNOWN": 0.5,
        }.get(self.regime, 0.5)

    def status(self) -> dict:
        return {
            "regime": self.regime,
            "confidence": round(self.confidence, 1),
            "size_mult": self.size_multiplier(),
        }

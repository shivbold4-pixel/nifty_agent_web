"""Candle features ? 10 pattern-based features from OHLC bars."""
import numpy as np
import pandas as pd

def compute_candle_features(df):
    if len(df) < 5:
        return _empty_features()
    df = df.sort_values("timestamp").reset_index(drop=True)
    candles = df.tail(10).reset_index(drop=True)
    latest = candles.iloc[-1]
    o, h, l, c = float(latest["open"]), float(latest["high"]), float(latest["low"]), float(latest["close"])
    rng = max(h - l, 1e-6)
    body = abs(c - o)
    body_ratio = body / rng
    upper_wick = (h - max(o, c)) / rng
    lower_wick = (min(o, c) - l) / rng
    prev = candles.iloc[-2]
    po, pc = float(prev["open"]), float(prev["close"])
    prev_bull = pc > po
    cur_bull = c > o
    engulfing = 0.0
    if cur_bull and not prev_bull and c > po and o < pc:
        engulfing = 1.0
    elif not cur_bull and prev_bull and c < po and o > pc:
        engulfing = -1.0
    doji = 1.0 if body_ratio < 0.1 else 0.0
    closes = candles["close"].values
    deltas = np.diff(closes)
    consec = 0
    direction = 0
    for d in reversed(deltas):
        sgn = 1 if d > 0 else (-1 if d < 0 else 0)
        if sgn == 0: break
        if direction == 0:
            direction = sgn; consec = 1
        elif sgn == direction:
            consec += 1
        else:
            break
    sizes = (candles["high"] - candles["low"]).values
    if len(sizes) >= 3 and np.std(sizes) > 1e-6:
        size_z = (sizes[-1] - np.mean(sizes)) / np.std(sizes)
    else:
        size_z = 0.0
    if len(candles) >= 3:
        hh = 1.0 if candles["high"].iloc[-1] > candles["high"].iloc[-2] > candles["high"].iloc[-3] else 0.0
        ll = 1.0 if candles["low"].iloc[-1] < candles["low"].iloc[-2] < candles["low"].iloc[-3] else 0.0
        hh_ll = hh - ll
    else:
        hh_ll = 0.0
    if "volume" in candles.columns and candles["volume"].sum() > 0:
        vw = (candles["close"] * candles["volume"]).sum() / candles["volume"].sum()
        drift = (c - vw) / max(abs(vw), 1e-6)
    else:
        drift = 0.0
    gap = (o - pc) / max(abs(pc), 1e-6)
    return {
        "body_ratio": round(float(body_ratio), 4),
        "upper_wick": round(float(upper_wick), 4),
        "lower_wick": round(float(lower_wick), 4),
        "engulfing": round(float(engulfing), 4),
        "doji": round(float(doji), 4),
        "consecutive": int(consec) * direction,
        "size_zscore": round(float(size_z), 4),
        "hh_ll": round(float(hh_ll), 4),
        "vw_drift": round(float(drift), 6),
        "gap": round(float(gap), 6),
    }

def _empty_features():
    return {"body_ratio": 0.0, "upper_wick": 0.0, "lower_wick": 0.0,
            "engulfing": 0.0, "doji": 0.0, "consecutive": 0,
            "size_zscore": 0.0, "hh_ll": 0.0, "vw_drift": 0.0, "gap": 0.0}

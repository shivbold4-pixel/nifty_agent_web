def compute_volume_profile(df, price_col="strike", volume_col=None, value_area_pct=0.70):
    import numpy as np, pandas as pd
    if volume_col is None:
        if "call_oi" in df.columns and "put_oi" in df.columns:
            df = df.copy(); df["_vol"] = df["call_oi"].fillna(0) + df["put_oi"].fillna(0)
            volume_col = "_vol"
        else:
            raise ValueError("No OI column")
    df = df[[price_col, volume_col]].dropna().sort_values(price_col)
    prices = df[price_col].values; vols = df[volume_col].values
    if len(prices) < 3: return {"poc": None, "vah": None, "val": None, "profile": {}}
    poc_idx = int(np.argmax(vols)); poc = float(prices[poc_idx])
    total_vol = vols.sum(); target = total_vol * value_area_pct
    lo, hi = poc_idx, poc_idx; captured = vols[poc_idx]
    while captured < target and (lo > 0 or hi < len(vols) - 1):
        lv = vols[lo - 1] if lo > 0 else -1
        rv = vols[hi + 1] if hi < len(vols) - 1 else -1
        if rv >= lv: hi += 1; captured += vols[hi]
        else: lo -= 1; captured += vols[lo]
    return {"poc": poc, "vah": float(prices[hi]), "val": float(prices[lo]),
            "profile": {float(p): float(v) for p, v in zip(prices, vols)}}

def volume_profile_features(df, spot):
    import numpy as np
    vp = compute_volume_profile(df)
    if vp["poc"] is None:
        return {"poc": 0.0, "vah": 0.0, "val": 0.0, "vp_position": 0.0, "vp_distance_poc": 0.0}
    poc, vah, val = vp["poc"], vp["vah"], vp["val"]
    vp_pos = (spot - val) / (vah - val) if vah > val else 0.5
    return {"poc": poc, "vah": vah, "val": val,
            "vp_position": float(np.clip(vp_pos, -1, 2)),
            "vp_distance_poc": (spot - poc) / max(spot, 1)}

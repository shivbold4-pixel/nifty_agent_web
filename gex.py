from math import log, sqrt, exp, pi
import numpy as np
import pandas as pd

def _bs_gamma(S, K, T, sigma):
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0: return 0.0
    d1 = (log(S/K) + 0.5*sigma*sigma*T) / (sigma*sqrt(T))
    return exp(-0.5*d1*d1) / sqrt(2*pi) / (S*sigma*sqrt(T))

def compute_gex(df, spot, days_to_expiry=7.0):
    T = max(days_to_expiry, 1.0) / 365.0
    total_call = total_put = 0.0
    for _, row in df.iterrows():
        strike = float(row.get("strike", 0))
        if strike <= 0: continue
        call_oi = float(row.get("call_oi", 0) or 0)
        put_oi  = float(row.get("put_oi", 0) or 0)
        c_iv = float(row.get("call_iv", 0) or 0) / 100.0 or 0.15
        p_iv = float(row.get("put_iv", 0) or 0) / 100.0 or 0.15
        cg = _bs_gamma(spot, strike, T, c_iv) * call_oi * spot * spot * 0.01 * 65
        pg = _bs_gamma(spot, strike, T, p_iv) * put_oi * spot * spot * 0.01 * 65
        total_call += cg; total_put += pg
    return {"net_gex": total_call - total_put,
            "total_call_gamma": total_call, "total_put_gamma": total_put,
            "zero_gamma": None, "gex_by_strike": {}}

def gex_features(df, spot):
    r = compute_gex(df, spot)
    net = r["net_gex"]
    total = abs(r["total_call_gamma"]) + abs(r["total_put_gamma"]) + 1e-9
    return {"gex_net": net, "gex_normalized": float(np.tanh(net/total)),
            "gex_zero_gamma": 0.0,
            "gex_regime": "POSITIVE_GAMMA" if net > 0 else "NEGATIVE_GAMMA" if net < 0 else "NEUTRAL"}

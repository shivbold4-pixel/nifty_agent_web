from pathlib import Path
import re

p = Path("agent.py")
src = p.read_text(encoding="utf-8")
changes = 0

# ---------- Find current option_features return statement ----------
old_return = '''    return {
        "spot": spot, "atm": atm, "pcr": pcr, "pcr_change": pcr_change,
        "iv_skew": iv_skew, "wall_asymmetry": wall_asym,
        "straddle_bps": straddle / max(spot, 1) * 1e4,
        "call_wall": call_wall, "put_wall": put_wall, "straddle": straddle,
    }'''

new_return = '''    # ---------- Extra features for v3 model ----------
    # 1. vol_ratio
    try:
        total_call_vol = df.call_volume.sum() if "call_volume" in df.columns else 0
        total_put_vol = df.put_volume.sum() if "put_volume" in df.columns else 0
        vol_ratio = total_put_vol / max(total_call_vol, 1)
    except Exception:
        vol_ratio = 1.0

    # 2. wall_asym (v3 name ? same as wall_asymmetry)
    wall_asym = wall_asym  # already computed above

    # 3. max_pain_dist
    try:
        strikes = df.strike.values
        pain = []
        for s in strikes:
            cp = ((s - df.strike).clip(lower=0) * df.call_oi).sum()
            pp = ((df.strike - s).clip(lower=0) * df.put_oi).sum()
            pain.append(cp + pp)
        max_pain = float(strikes[int(np.argmin(pain))])
        max_pain_dist = (max_pain - spot) / max(spot, 1)
    except Exception:
        max_pain = 0.0
        max_pain_dist = 0.0

    # 4. days_to_expiry ? from expiry column if present, else 7
    try:
        if "expiry" in df.columns:
            exp_str = str(df["expiry"].iloc[0])
            exp_dt = pd.to_datetime(exp_str)
            dte = (exp_dt - pd.Timestamp.now()).total_seconds() / 86400.0
            dte = max(dte, 0.0)
        else:
            dte = 7.0
    except Exception:
        dte = 7.0

    # 5. pc_premium_ratio (ATM put price / call price)
    try:
        pc_premium_ratio = float(atm_row.put_ltp) / (float(atm_row.call_ltp) + 1e-6)
    except Exception:
        pc_premium_ratio = 1.0

    return {
        "spot": spot, "atm": atm, "pcr": pcr, "pcr_change": pcr_change,
        "iv_skew": iv_skew, "wall_asymmetry": wall_asym, "wall_asym": wall_asym,
        "straddle_bps": straddle / max(spot, 1) * 1e4,
        "call_wall": call_wall, "put_wall": put_wall, "straddle": straddle,
        "vol_ratio": vol_ratio,
        "max_pain_dist": max_pain_dist,
        "days_to_expiry": dte,
        "pc_premium_ratio": pc_premium_ratio,
    }'''

if old_return in src:
    src = src.replace(old_return, new_return, 1)
    changes += 1
    print("[OK] option_features() now returns 7 additional fields")
else:
    print("[WARN] Could not find exact option_features return block")
    # Try to find it with regex
    pattern = r'    return \{\s*"spot": spot.*?"straddle": straddle,\s*\}'
    match = re.search(pattern, src, re.DOTALL)
    if match:
        src = src[:match.start()] + new_return + src[match.end():]
        changes += 1
        print("[OK] Patched via regex")
    else:
        print("[ERROR] Return block not found ? need manual inspection")

p.write_text(src, encoding="utf-8")
print(f"Changes: {changes}")

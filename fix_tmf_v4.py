from pathlib import Path

p = Path("trend_maturity.py")
src = p.read_text(encoding="utf-8")

# Find the SUPPRESSION FACTOR section
old = '''        # ============================================================
        # SUPPRESSION FACTOR
        # ============================================================
        if is_parabolic:
            suppression = 0.25
            state = "PARABOLIC"
        elif is_exhausted:
            suppression = 0.35
            state = "EXHAUSTED"
        elif is_healthy_trend:
            suppression = 1.0
            state = "HEALTHY_TREND"
        elif is_choppy:
            suppression = 0.6
            state = "CHOPPY"
        else:
            suppression = 0.85
            state = "NEUTRAL"'''

new = '''        # ============================================================
        # VWAP SLOPE ? Distinguish healthy trend from exhaustion
        # ============================================================
        # vwap_slope was computed earlier (late_vwap - early_vwap) / early_vwap
        # Positive = rising trend, Negative = falling trend, Near-zero = flat

        # VWAP slope is meaningful only if price is trending in same direction
        trend_up_healthy = vwap_slope > 0.0004 and overall_move > 0
        trend_down_healthy = vwap_slope < -0.0004 and overall_move < 0

        # ============================================================
        # SUPPRESSION FACTOR (v4 ? VWAP slope aware)
        # ============================================================
        if is_parabolic:
            suppression = 0.25
            state = "PARABOLIC"
        elif is_exhausted and not (trend_up_healthy or trend_down_healthy):
            suppression = 0.35
            state = "EXHAUSTED"
        elif is_exhausted and (trend_up_healthy or trend_down_healthy):
            # Trend is exhausted BUT VWAP is trending ? softer suppression
            suppression = 0.75
            state = "TRENDING_EXTENDED"
        elif is_healthy_trend:
            suppression = 1.0
            state = "HEALTHY_TREND"
        elif trend_up_healthy or trend_down_healthy:
            # VWAP confirms trend but TMF didn't flag as healthy
            suppression = 0.95
            state = "TRENDING"
        elif is_choppy:
            suppression = 0.6
            state = "CHOPPY"
        else:
            suppression = 0.85
            state = "NEUTRAL"'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print("[OK] VWAP slope detection added to TMF")
else:
    print("[SKIP] Pattern not found ? check trend_maturity.py")
    # Show current suppression section
    lines = src.split("\n")
    for i, line in enumerate(lines):
        if "suppression" in line.lower() and "=" in line and "is_" in line:
            print(f"  Line {i+1}: {line}")

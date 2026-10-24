from pathlib import Path

p = Path("agent.py")
src = p.read_text(encoding="utf-8")
changes = 0

# ============================================================
# FIX 1 ? VWAP DISTANCE GATE
# ============================================================
# Insert after the TMF computation block, before momentum
vwap_block = '''        # ============================================================
        # VWAP DISTANCE GATE
        # If Nifty is too far from VWAP, force FLAT.
        # ============================================================
        vwap_gate_active = False
        vwap_distance_pct = 0.0
        if len(self.recent_spots) >= 5:
            _spots = [s[1] for s in self.recent_spots[-20:]]
            _weights = list(range(1, len(_spots) + 1))
            _vwap = sum(p * w for p, w in zip(_spots, _weights)) / sum(_weights)
            if _vwap > 0:
                vwap_distance_pct = (_spot_now - _vwap) / _vwap
                if abs(vwap_distance_pct) >= 0.0075:
                    vwap_gate_active = True

'''

anchor1 = "        # ============================================================\n        # MULTI-TIMEFRAME MOMENTUM ENGINE"
if anchor1 in src and "VWAP DISTANCE GATE" not in src:
    src = src.replace(anchor1, vwap_block + anchor1, 1)
    changes += 1
    print("[OK] Fix 1: VWAP distance gate added")
else:
    print("[SKIP] Fix 1: already present or anchor missing")

# ============================================================
# FIX 2 ? TMF AGGRESSIVE THRESHOLD
# ============================================================
old_sup = '''        # ---- TMF v2 Suppression ----
        blended *= tmf_suppression

        if tmf_hint == 1 and blended < 0:
            blended *= 0.5
        elif tmf_hint == -1 and blended > 0:
            blended *= 0.5'''

new_sup = '''        # ---- TMF v2 Suppression (AGGRESSIVE) ----
        blended *= tmf_suppression

        # Aggressive mode: exhaustion >= 0.5 forces FLAT
        if tmf_score >= 0.5:
            blended *= 0.25

        if tmf_hint == 1 and blended < 0:
            blended *= 0.4
        elif tmf_hint == -1 and blended > 0:
            blended *= 0.4

        # ---- VWAP DISTANCE GATE ----
        if vwap_gate_active:
            blended *= 0.15'''

if old_sup in src:
    src = src.replace(old_sup, new_sup, 1)
    changes += 1
    print("[OK] Fix 2: TMF aggressive threshold applied")
else:
    print("[SKIP] Fix 2: pattern not found or already aggressive")

# ============================================================
# FIX 3 ? SIGNAL COOLDOWN
# ============================================================
# Add cooldown tracking to __init__
old_init = "        self.tmf = TrendMaturityFilter()"
new_init = "        self.tmf = TrendMaturityFilter()\n        self._last_signal_direction = None\n        self._last_signal_time = 0.0"

if old_init in src and "self._last_signal_direction" not in src:
    src = src.replace(old_init, new_init, 1)
    changes += 1
    print("[OK] Fix 3a: Cooldown state added to init")
else:
    print("[SKIP] Fix 3a: already present or pattern missing")

# Add cooldown logic before direction determination
anchor_cooldown = "        th = self.cfg[\"agent\"][\"direction_threshold\"]"
cooldown_block = '''        # ---- SIGNAL COOLDOWN ----
        import time as _time
        _now_ts = _time.time()
        _new_direction = "BULLISH" if blended > 0.35 else ("BEARISH" if blended < -0.35 else "FLAT")

        if (self._last_signal_direction is not None
                and self._last_signal_direction == _new_direction
                and _new_direction != "FLAT"
                and (_now_ts - self._last_signal_time) < 900):  # 15 min
            # Same direction within 15 min ? halve confidence
            blended *= 0.5

        if _new_direction != "FLAT":
            self._last_signal_direction = _new_direction
            self._last_signal_time = _now_ts

        th = self.cfg["agent"]["direction_threshold"]'''

if anchor_cooldown in src and "SIGNAL COOLDOWN" not in src:
    src = src.replace(anchor_cooldown, cooldown_block, 1)
    changes += 1
    print("[OK] Fix 3b: Cooldown logic applied")
else:
    print("[SKIP] Fix 3b: already present or anchor missing")

# Add cooldown fields to contributions
old_c = '"tmf_state": tmf_state,'
new_c = '"tmf_state": tmf_state,\n                           "vwap_gate": vwap_gate_active,\n                           "vwap_dist_pct": round(vwap_distance_pct * 100, 3),'

if old_c in src and "vwap_gate" not in src:
    src = src.replace(old_c, new_c, 1)
    changes += 1
    print("[OK] Fix 3c: VWAP gate added to contributions")

p.write_text(src, encoding="utf-8")
print()
print("=" * 50)
print(f"ALL FIXES APPLIED ({changes} changes)")
print("=" * 50)

from pathlib import Path

p = Path("agent.py")
src = p.read_text(encoding="utf-8")

# Find the volatility inference block start
anchor = "        # ==================================================\n        # VOLATILITY MODEL C inference"

momentum_block = '''        # ==================================================
        # MOMENTUM FEATURES (for v3 model)
        # ==================================================
        try:
            if len(self.recent_spots) >= 2:
                _now = self.recent_spots[-1][1]
                _prev = self.recent_spots[-2][1]
                combined_feats["mom_5m"] = (_now - _prev) / _prev if _prev > 0 else 0.0
            else:
                combined_feats["mom_5m"] = 0.0

            if len(self.recent_spots) >= 4:
                _now = self.recent_spots[-1][1]
                _prev = self.recent_spots[-4][1]
                combined_feats["mom_15m"] = (_now - _prev) / _prev if _prev > 0 else 0.0
            else:
                combined_feats["mom_15m"] = 0.0
        except Exception as _e:
            print(f"[agent] momentum error: {_e}")
            combined_feats["mom_5m"] = 0.0
            combined_feats["mom_15m"] = 0.0

'''

if anchor in src and "MOMENTUM FEATURES (for v3 model)" not in src:
    src = src.replace(anchor, momentum_block + anchor, 1)
    print("[OK] Momentum feature block inserted")
else:
    print("[SKIP] Already present or anchor missing")

p.write_text(src, encoding="utf-8")
print("DONE")

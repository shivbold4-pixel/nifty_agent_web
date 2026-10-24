from pathlib import Path
p = Path("agent.py")
src = p.read_text(encoding="utf-8")

old = '''        # ============================================================
        # TREND MATURITY FILTER v2
        # ============================================================
        self.tmf.update(_spot_now)'''

new = '''        # ============================================================
        # TREND MATURITY FILTER v2
        # ============================================================
        _spot_now = self.last_option_feats["spot"]
        self.tmf.update(_spot_now)'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print("[OK] Fixed")
else:
    print("[SKIP] Already fixed or pattern not found")

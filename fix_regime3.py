from pathlib import Path
p = Path("agent.py")
src = p.read_text(encoding="utf-8")

old = "        self.vol_model = VolatilityModel()\n        self.risk = RiskManager()"
new = "        self.vol_model = VolatilityModel()\n        self.risk = RiskManager()\n        self.regime_detector = RegimeDetector()"

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print("[OK] regime_detector initialized")
elif "self.regime_detector = RegimeDetector()" in src:
    print("[SKIP] Already initialized")
else:
    # Try alternate pattern
    old2 = "        self.vol_model = VolatilityModel()"
    new2 = "        self.vol_model = VolatilityModel()\n        self.regime_detector = RegimeDetector()"
    if old2 in src:
        src = src.replace(old2, new2, 1)
        p.write_text(src, encoding="utf-8")
        print("[OK] regime_detector initialized (alternate)")
    else:
        print("[ERROR] Cannot find pattern")

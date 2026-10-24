from pathlib import Path

p = Path("auto_fetcher.py")
src = p.read_text(encoding="utf-8")

old = '"features": _clean_features(pred.features),'
new = '''"features": {
            **_clean_features(pred.features),
            "vol_conf": float(getattr(pred, "volatility_conf", 0) or 0),
            "vol_label": str(getattr(pred, "volatility", "UNKNOWN")),
            "regime": str(pred.regime),
        },'''

if old in src:
    src = src.replace(old, new, 1)
    p.write_text(src, encoding="utf-8")
    print("[OK] features now include vol_conf + regime")
else:
    print("[SKIP] Pattern not found or already patched")
    # Show current lines around save
    for i, line in enumerate(src.split("\n")):
        if '"features"' in line:
            print(f"  Line {i+1}: {line}")

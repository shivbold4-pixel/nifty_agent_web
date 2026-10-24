from pathlib import Path

p = Path("trend_maturity.py")
if not p.exists():
    print("File not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()
fixed = False

# Find the specific lines and indent them correctly
for i, line in enumerate(lines):
    if "trend_up_healthy =" in line or "trend_down_healthy =" in line or "# Calculate VWAP slope health" in line:
        if not line.startswith("        "): # If it's missing the 8 spaces
            lines[i] = "        " + line.strip()
            fixed = True

if fixed:
    p.write_text("\n".join(lines), encoding="utf-8")
    print("[OK] Indentation fixed perfectly for the VWAP variables!")
else:
    print("[SKIP] Lines were already indented correctly.")

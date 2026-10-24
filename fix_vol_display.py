from pathlib import Path

p = Path("agent.py")
src = p.read_text(encoding="utf-8")

# Show current action_note usage
print("=== Current action_note references ===")
for i, line in enumerate(src.split("\n")):
    if "action_note" in line or "(Low vol" in line or "(High vol" in line:
        print(f"  Line {i+1}: {line.strip()}")

# Apply fix: replace hardcoded text with dynamic label
fixes = [
    ('action_note = " (Low vol - size down)"',
     'action_note = f" (Vol: {vol_label})" if vol_label != "UNKNOWN" else ""'),
    ('action_note = " (High vol - size up)"',
     'action_note = f" (Vol: {vol_label})" if vol_label != "UNKNOWN" else ""'),
    ('action_note = " (Low vol - size down)"  # fallback',
     'action_note = f" (Vol: {vol_label})" if vol_label != "UNKNOWN" else ""'),
]

changes = 0
for old, new in fixes:
    if old in src:
        src = src.replace(old, new)
        changes += 1
        print(f"[OK] Replaced: {old[:50]}")

p.write_text(src, encoding="utf-8")
print(f"\nTotal changes: {changes}")

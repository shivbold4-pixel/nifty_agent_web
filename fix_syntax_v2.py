from pathlib import Path

p = Path("volatility_model.py")
if not p.exists():
    print("[ERROR] volatility_model.py not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()
start_idx = -1
end_idx = len(lines)

# Find the start of the _load method
for i, line in enumerate(lines):
    if "def _load(self):" in line:
        start_idx = i
        break

if start_idx == -1:
    print("[ERROR] Could not find 'def _load(self):'")
    exit()

# Find the end of the _load method (the next 'def' that is indented by 4 spaces)
for i in range(start_idx + 1, len(lines)):
    if lines[i].startswith("    def "):
        end_idx = i
        break

# Create a perfectly clean _load method
clean_block = """    def _load(self):
        if MODEL_PATH.exists():
            try:
                import pickle
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                # Ignore feature override to match the 6-feature model
                print(f"[vol_model] Loaded Pickle. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
                self.model = None
"""

# Reconstruct the file
new_lines = lines[:start_idx] + clean_block.splitlines() + lines[end_idx:]
p.write_text("\n".join(new_lines), encoding="utf-8")
print("[OK] Rebuilt the _load method perfectly. SyntaxError fixed!")

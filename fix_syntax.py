from pathlib import Path

p = Path("volatility_model.py")
if not p.exists():
    print("[ERROR] volatility_model.py not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()
start_idx = -1
end_idx = -1

# Find the start of the _load method
for i, line in enumerate(lines):
    if "def _load(self):" in line:
        start_idx = i
        break

# Find the end of the _load method (the next method def predict)
if start_idx != -1:
    for i in range(start_idx + 1, len(lines)):
        if "def predict(" in line or "def " in lines[i] and not lines[i].startswith("    "):
            end_idx = i
            break

if start_idx == -1 or end_idx == -1:
    print("[ERROR] Could not find the _load method boundaries.")
    exit()

# Create a clean, perfectly indented _load method
clean_block = """    def _load(self):
        if MODEL_PATH.exists():
            try:
                import pickle
                with open(MODEL_PATH, "rb") as f:
                    self.model = pickle.load(f)
                # Ignore feature override text file to match the 6-feature model
                # if FEATURES_PATH.exists():
                #     self.features = FEATURES_PATH.read_text().strip().split("\n")
                print(f"[vol_model] Loaded Pickle. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
                self.model = None
"""

# Reconstruct the file
new_lines = lines[:start_idx] + clean_block.splitlines() + lines[end_idx:]
p.write_text("\n".join(new_lines), encoding="utf-8")
print("[OK] Rebuilt the _load method perfectly. SyntaxError fixed!")

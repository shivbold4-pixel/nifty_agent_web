from pathlib import Path

p = Path("volatility_model.py")
if not p.exists():
    print("[ERROR] volatility_model.py not found.")
    exit()

lines = p.read_text(encoding="utf-8").splitlines()
start_idx = -1
end_idx = len(lines)

# Find the _load method
for i, line in enumerate(lines):
    if "def _load(self):" in line:
        start_idx = i
        break

if start_idx == -1:
    print("[ERROR] Could not find 'def _load(self):'")
    exit()

# Find the end of the _load method
for i in range(start_idx + 1, len(lines)):
    if lines[i].startswith("    def "):
        end_idx = i
        break

# Create the bulletproof _load method
clean_block = """    def _load(self):
        if MODEL_PATH.exists():
            try:
                import pickle
                with open(MODEL_PATH, "rb") as f:
                    loaded_data = pickle.load(f)
                
                # If the .pkl is a dictionary, extract the actual model
                if isinstance(loaded_data, dict):
                    if 'model' in loaded_data:
                        self.model = loaded_data['model']
                    elif 'xgb_model' in loaded_data:
                        self.model = loaded_data['xgb_model']
                    else:
                        print(f"[vol_model] ERROR: Could not find model in dict. Keys: {loaded_data.keys()}")
                        self.model = None
                else:
                    # It's already the model object
                    self.model = loaded_data
                    
                print(f"[vol_model] Loaded Pickle. Features: {self.features}")
            except Exception as e:
                print(f"[vol_model] Load failed: {e}")
                self.model = None
"""

# Reconstruct the file
new_lines = lines[:start_idx] + clean_block.splitlines() + lines[end_idx:]
p.write_text("\n".join(new_lines), encoding="utf-8")
print("[OK] Rebuilt the _load method to handle dictionaries perfectly!")

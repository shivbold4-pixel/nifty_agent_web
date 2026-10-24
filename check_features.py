import os
import json

# Search the entire folder and subfolders for the model file
model_path = None
for root, dirs, files in os.walk("."):
    for file in files:
        if file.endswith(".json") and ("xgb" in file.lower() or "model" in file.lower() or "volatility" in file.lower()):
            model_path = os.path.join(root, file)
            break
    if model_path:
        break

if not model_path:
    print("[ERROR] Could not find any JSON model file in this folder or subfolders.")
    exit()

print(f"[OK] Found model file at: {model_path}\n")

try:
    with open(model_path, 'r', encoding='utf-8') as f:
        model = json.load(f)
        
        # Check different standard XGBoost JSON structures
        if 'learner' in model and 'feature_names' in model['learner']:
            features = model['learner']['feature_names']
        elif 'feature_names' in model:
            features = model['feature_names']
        else:
            print("[ERROR] Could not find 'feature_names' inside the model JSON.")
            exit()
             
        print("=== THE MODEL EXPECTS THESE FEATURES ===")
        for i, feat in enumerate(features):
            print(f"{i+1}. {feat}")
        print("========================================\n")
        
except Exception as e:
    print(f"[ERROR] Could not read model file. Error: {e}")

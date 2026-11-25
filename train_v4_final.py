import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, classification_report
from sklearn.utils.class_weight import compute_sample_weight
from pathlib import Path

csv_path = "v4_clean_training_data.csv"
if not Path(csv_path).exists():
    print("[ERROR] v4_clean_training_data.csv not found. Run backfill_v4.py first.")
    exit()

print(f"[OK] Loading clean data from {csv_path}...")
df = pd.read_csv(csv_path)

features = ['pcr', 'pcr_change', 'wall_asym', 'vol_ratio', 'straddle']
target = 'label'

# Map [-1, 0, 1] to [0, 1, 2] for XGBoost
label_map = {-1: 0, 0: 1, 1: 2}
reverse_label_map = {0: -1, 1: 0, 2: 1}

df[features] = df[features].fillna(0.0)
df = df.dropna(subset=[target])
df['label_mapped'] = df[target].map(label_map)

X = df[features]
y = df['label_mapped']

# Strict Chronological Split (80% Train, 20% Test)
split_idx = int(len(df) * 0.8)
X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

print(f"Train size: {len(X_train)} rows (The Past)")
print(f"Test size:  {len(X_test)} rows (The Future)")

# Calculate balanced class weights to fix the "cheat code" bias
print("\n[OK] Calculating balanced sample weights...")
sample_weights = compute_sample_weight(class_weight='balanced', y=y_train)

# Train the V4 Model
model = xgb.XGBClassifier(
    n_estimators=150,
    max_depth=3,
    learning_rate=0.05,
    objective='multi:softprob',
    num_class=3,
    random_state=42
)

print("[OK] Training XGBoost V4 model with balanced weights...")
model.fit(X_train, y_train, sample_weight=sample_weights)

print("\n[OK] Evaluating on unseen future data...")
preds_mapped = model.predict(X_test)
preds_original = [reverse_label_map[p] for p in preds_mapped]
y_test_original = [reverse_label_map[v] for v in y_test]

accuracy = accuracy_score(y_test_original, preds_original)

print(f"\n=== V4 FINAL ACCURACY: {accuracy:.4f} ({accuracy*100:.2f}%) ===")
print("\nClassification Report:")
print(classification_report(y_test_original, preds_original))

Path("models").mkdir(exist_ok=True)
model.save_model("models/xgb_v4_final.json")
print("[OK] V4 Final Model saved to models/xgb_v4_final.json")

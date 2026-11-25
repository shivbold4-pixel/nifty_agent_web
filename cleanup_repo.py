import os
from pathlib import Path

# Define the patterns of temporary files to delete
temp_patterns = [
    "patch_", 
    "fix_", 
    "create_", 
    "test_fetch", 
    "dns_test",
    "rescue_",
    "sunday_surgery",
    "backfill_v4"
]

# Keep these critical files
keep_files = ["auto_fetcher_v2.py", "agent.py", "app.py", "volatility_model.py", "trend_maturity.py", "triple_barrier.py"]

deleted_count = 0
print("[OK] Scanning for temporary patch scripts...")

for file in os.listdir("."):
    if file.endswith(".py") and file not in keep_files:
        # Check if the file matches our temporary patterns
        if any(file.startswith(pattern) for pattern in temp_patterns):
            try:
                os.remove(file)
                print(f"Deleted: {file}")
                deleted_count += 1
            except Exception as e:
                print(f"Could not delete {file}: {e}")

print(f"\n[OK] Cleanup complete! Removed {deleted_count} temporary files.")
print("Your repository is now clean and ready for production.")

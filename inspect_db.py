import os
import json
from supabase import create_client, Client

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")

if not url or not key:
    print("[ERROR] Please set SUPABASE_URL and SUPABASE_KEY first.")
    exit()

print("[OK] Connecting to Supabase...")
supabase: Client = create_client(url, key)

try:
    # Let's check the live_data table first
    print("\n=== Checking live_data table ===")
    res = supabase.table("live_data").select("*").limit(1).execute()
    if res.data:
        row = res.data[0]
        print("Columns available:", list(row.keys()))
        if "chain_json" in row and row["chain_json"]:
            print("Sample chain_json (first 500 chars):")
            print(str(row["chain_json"])[:500] + "...")
    else:
        print("No rows found in live_data.")

    # Let's check predictions_v4
    print("\n=== Checking predictions_v4 table ===")
    res2 = supabase.table("predictions_v4").select("*").limit(1).execute()
    if res2.data:
        row2 = res2.data[0]
        print("Columns available:", list(row2.keys()))
    else:
        print("No rows found in predictions_v4.")
        
except Exception as e:
    print(f"[ERROR] Database error: {e}")

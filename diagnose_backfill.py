import os
import json
import pandas as pd
from supabase import create_client, Client
from agent import option_features

url = os.environ.get("SUPABASE_URL")
key = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

print("[OK] Fetching 15 rows for diagnostic...")
res = supabase.table("live_data").select("*").order("ts_ist", desc=False).limit(15).execute()
rows = res.data

if len(rows) < 15:
    print(f"[ERROR] Only found {len(rows)} rows. Need at least 15 for look-ahead.")
    exit()

# Test the very first row
row = rows[0]
print("\n--- DIAGNOSTIC FOR ROW 0 ---")
print(f"Spot: {row.get('nifty_spot')}")
print(f"Chain JSON type: {type(row.get('chain_json'))}")

try:
    chain_list = json.loads(row["chain_json"])
    print(f"Chain List length: {len(chain_list)}")
    print(f"First strike in chain: {chain_list[0]}")
    
    df = pd.DataFrame(chain_list)
    print(f"DataFrame columns: {list(df.columns)}")
    
    spot = float(row["nifty_spot"])
    feats = option_features(df, spot=spot)
    print(f"Features calculated successfully: {feats}")
    
except Exception as e:
    print(f"\n[ERROR FOUND] Failed to process features: {e}")

try:
    # Check future spots
    future_spots = [r["nifty_spot"] for r in rows[1:13] if r.get("nifty_spot")]
    print(f"\nFuture spots found: {len(future_spots)}")
    if len(future_spots) < 12:
        print("[ERROR] Not enough future spots to label this row.")
        
except Exception as e:
    print(f"\n[ERROR FOUND] Failed to get future spots: {e}")

import time
import pandas as pd
from datetime import datetime, timedelta, date
from pathlib import Path
from breeze_connect import BreezeConnect

API_KEY    = "u&l904368E315~56B58p6y7157524343"
SECRET_KEY = "530S14_28082F1Y449(9M481285q4373"
USER_ID    = "7706886483"
PASSWORD   = "shivam411996"
SESSION_TOKEN = input("Paste today's Session Token: ").strip()

OUT_DIR = Path("data/historical")
OUT_DIR.mkdir(parents=True, exist_ok=True)

print("[breeze] Authenticating...")
breeze = BreezeConnect(api_key=API_KEY)
breeze.generate_session(api_secret=SECRET_KEY, session_token=SESSION_TOKEN)
print("[breeze] Auth OK")

TODAY = date.today()
START_DATE = TODAY - timedelta(days=365 * 3)

def chunks(start, end, step_days=2):
    d = start
    while d < end:
        yield d, min(d + timedelta(days=step_days), end)
        d += timedelta(days=step_days)

def fetch_series(stock_code, exchange, product_type, label):
    all_rows = []
    chunk_list = list(chunks(START_DATE, TODAY))
    print(f"[breeze] Fetching {label} ({len(chunk_list)} chunks)...")
    for i, (cs, ce) in enumerate(chunk_list):
        from_dt = cs.strftime("%Y-%m-%dT09:15:00.000Z")
        to_dt   = ce.strftime("%Y-%m-%dT15:30:00.000Z")
        try:
            resp = breeze.get_historical_data_v2(
                interval="1minute",
                from_date=from_dt, to_date=to_dt,
                stock_code=stock_code, exchange_code=exchange,
                product_type=product_type,
            )
            if isinstance(resp, dict) and resp.get("Success"):
                for row in resp["Success"]:
                    all_rows.append({
                        "datetime": row["datetime"],
                        "close": float(row["close"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                    })
                print(f"    [{i+1}/{len(chunk_list)}] {cs} -> {ce}: {len(resp['Success'])} rows")
            else:
                print(f"    [{i+1}/{len(chunk_list)}] {cs} -> {ce}: no data")
        except Exception as e:
            print(f"    [error] {cs}: {str(e)[:80]}")
        time.sleep(0.5)
    if not all_rows:
        print(f"[breeze] {label}: NO DATA")
        return None
    df = pd.DataFrame(all_rows)
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.drop_duplicates(subset=["datetime"]).sort_values("datetime").reset_index(drop=True)
    print(f"[breeze] {label}: {len(df)} rows")
    return df

nifty = fetch_series("NIFTY", "NSE", "cash", "Nifty Spot")
if nifty is not None:
    nifty.to_parquet(OUT_DIR / "nifty_spot_3y.parquet", index=False)
    print("[saved] nifty_spot_3y.parquet")

for code in ["INDIAVIX", "VIX"]:
    print(f"\n[breeze] Trying VIX code: {code}")
    vix = fetch_series(code, "NSE", "cash", f"VIX ({code})")
    if vix is not None and len(vix) > 100:
        vix.to_parquet(OUT_DIR / "india_vix_3y.parquet", index=False)
        print(f"[saved] india_vix_3y.parquet using {code}")
        break
    time.sleep(1)

print("\n[breeze] DONE.")

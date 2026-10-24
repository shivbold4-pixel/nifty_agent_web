"""
Download 3 years of Nifty option chain history from ICICI Breeze.
Uses dynamic strike ranges based on each expiry's Nifty spot level.
"""
import os
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

def get_thursdays(start, end):
    d = start
    while d.weekday() != 3:
        d += timedelta(days=1)
    while d <= end:
        yield d
        d += timedelta(days=7)

expiry_dates = list(get_thursdays(START_DATE, TODAY))
print(f"[breeze] Planning download for {len(expiry_dates)} expiries")

# Nifty spot at various historical periods (approx)
# We'll use a rough band around these to determine strikes
def approx_nifty_level(expiry_date):
    # Rough historical Nifty closing levels
    year = expiry_date.year
    month = expiry_date.month
    if year == 2023:
        return 19500 if month < 7 else 20500 if month < 10 else 19000
    if year == 2024:
        return 21500 if month < 5 else 22500 if month < 10 else 24000
    if year == 2025:
        return 23000 if month < 4 else 24500 if month < 8 else 25000
    return 24000

def fetch_spot(expiry_str):
    """Fetch Nifty spot on the day before expiry."""
    try:
        from_dt = (datetime.strptime(expiry_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%dT09:15:00.000Z")
        to_dt   = (datetime.strptime(expiry_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%dT15:30:00.000Z")
        resp = breeze.get_historical_data_v2(
            interval="1day",
            from_date=from_dt,
            to_date=to_dt,
            stock_code="NIFTY",
            exchange_code="NSE",
            product_type="cash",
        )
        if isinstance(resp, dict) and resp.get("Success"):
            return float(resp["Success"][-1]["close"])
    except Exception as e:
        print(f"    [spot error] {e}")
    return None


def fetch_one(strike, right, expiry_str):
    try:
        from_dt = (datetime.strptime(expiry_str, "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%dT00:00:00.000Z")
        to_dt   = (datetime.strptime(expiry_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%dT23:59:59.000Z")
        resp = breeze.get_historical_data_v2(
            interval="1minute",
            from_date=from_dt,
            to_date=to_dt,
            stock_code="NIFTY",
            exchange_code="NFO",
            product_type="options",
            expiry_date=expiry_str + "T06:00:00.000Z",
            right=right,
            strike_price=str(int(strike)),
        )
        if isinstance(resp, dict) and resp.get("Success"):
            return pd.DataFrame(resp["Success"])
        return None
    except Exception as e:
        return None


all_rows = []
for i, exp in enumerate(expiry_dates):
    exp_str = exp.strftime("%Y-%m-%d")
    print(f"\n[{i+1}/{len(expiry_dates)}] Expiry: {exp_str}")

    # Get spot ? try real, fallback to approx
    spot = fetch_spot(exp_str)
    if spot is None:
        spot = approx_nifty_level(exp)
        print(f"    [using approx spot] {spot}")
    else:
        print(f"    [spot] {spot}")

    # Pick ATM ?10 strikes
    atm = round(spot / 50) * 50
    strikes = [atm + (n * 50) for n in range(-10, 11)]

    rows_for_expiry = 0
    for strike in strikes:
        for right in ["call", "put"]:
            df = fetch_one(strike, right, exp_str)
            if df is not None and len(df):
                df["strike"] = strike
                df["right"] = right
                df["expiry"] = exp_str
                all_rows.append(df)
                rows_for_expiry += len(df)
                print(f"    ? {strike} {right}: {len(df)} rows")
            time.sleep(0.4)

    print(f"    [expiry total] {rows_for_expiry} rows")

    if all_rows:
        combined = pd.concat(all_rows, ignore_index=True)
        checkpoint_file = OUT_DIR / f"checkpoint_{exp_str}.parquet"
        combined.to_parquet(checkpoint_file, index=False)
        print(f"    [saved] total so far: {len(combined)} rows")

if all_rows:
    final = pd.concat(all_rows, ignore_index=True)
    final_file = OUT_DIR / "nifty_options_3y.parquet"
    final.to_parquet(final_file, index=False)
    print(f"\n[breeze] DONE. {len(final)} rows saved to {final_file}")
else:
    print("\n[breeze] Still no data. Something else is wrong.")

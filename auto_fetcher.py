"""
Automated NSE data fetcher (v7 ? DNS-safe).
- Supabase writes use direct HTTP (no supabase-py DNS issues)
- indiaopt import delayed until after Supabase handshake
- Aggressive DNS warm-up + retry
"""
import os
import time
import json
import socket
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from nselib import capital_market

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


def _get_env():
    url = os.environ.get("SUPABASE_URL", "").strip().strip('"').strip("'")
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")
    return url, key


def ensure_dns(url: str, max_attempts: int = 8) -> bool:
    """Force DNS resolution with retries before any heavy imports."""
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    for attempt in range(1, max_attempts + 1):
        try:
            ip = socket.gethostbyname(host)
            print(f"[auto_fetcher] DNS OK: {host} -> {ip}")
            return True
        except Exception as e:
            print(f"[auto_fetcher] DNS attempt {attempt}/{max_attempts}: {e}")
            time.sleep(2)
    return False


# ============================================================
# SUPABASE ? direct HTTP (no supabase-py)
# ============================================================
def supabase_insert(url: str, key: str, table: str, record: dict) -> bool:
    """POST to Supabase REST API directly."""
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for attempt in range(1, 4):
        try:
            r = requests.post(endpoint, json=record, headers=headers, timeout=15)
            if r.status_code in (200, 201, 204):
                return True
            print(f"[supabase] HTTP {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            err = str(e)
            if "getaddrinfo" in err or "11001" in err:
                print(f"[supabase] DNS error (attempt {attempt}/3), retrying...")
                time.sleep(3)
            else:
                print(f"[supabase] error: {e}")
                return False
    return False


# ============================================================
# NIFTY + VIX
# ============================================================
def fetch_nifty_and_vix() -> Tuple[Optional[float], Optional[float]]:
    try:
        df = capital_market.market_watch_all_indices()
        if df is None or len(df) == 0:
            return None, None

        sym_col, ltp_col = None, None
        for col in df.columns:
            cl = col.lower()
            if cl in ("indexsymbol", "index_symbol", "symbol", "index"):
                sym_col = col
            if cl in ("last", "ltp", "last_price", "lastprice"):
                ltp_col = col

        if not sym_col or not ltp_col:
            return None, None

        nifty, vix = None, None
        for _, row in df.iterrows():
            sym = str(row.get(sym_col, "")).strip().upper()
            try:
                val = float(str(row.get(ltp_col, "")).replace(",", ""))
            except (ValueError, TypeError):
                continue
            if sym == "NIFTY 50":
                nifty = val
            elif sym == "INDIA VIX":
                vix = val

        return nifty, vix
    except Exception as e:
        print(f"[auto_fetcher] Nifty/VIX error: {e}")
        return None, None


# ============================================================
# OPTION CHAIN ? lazy indiaopt import
# ============================================================
def fetch_option_chain(spot: float = None) -> Optional[list]:
    try:
        import asyncio
        from indiaopt import NSEClient  # <-- IMPORTANT: delayed import

        async def _fetch():
            async with NSEClient() as nse:
                result = await nse.fetch_option_chain("NIFTY")
                all_rows = []
                for row in result.atm_window(n=200):
                    all_rows.append({
                        "strike": float(row.strike),
                        "call_oi": float(row.call_oi or 0),
                        "call_oi_change": float(getattr(row, "call_oi_change", 0) or 0),
                        "call_ltp": float(row.call_ltp or 0),
                        "call_iv": float(getattr(row, "call_iv", 0) or 0),
                        "call_volume": float(getattr(row, "call_volume", 0) or 0),
                        "put_oi": float(row.put_oi or 0),
                        "put_oi_change": float(getattr(row, "put_oi_change", 0) or 0),
                        "put_ltp": float(row.put_ltp or 0),
                        "put_iv": float(getattr(row, "put_iv", 0) or 0),
                        "put_volume": float(getattr(row, "put_volume", 0) or 0),
                    })
                return all_rows

        all_rows = asyncio.run(_fetch())
        if not all_rows:
            return None

        if spot is None or spot <= 0:
            combined = {r["strike"]: r["call_oi"] + r["put_oi"] for r in all_rows}
            spot = max(combined, key=combined.get)

        window = 500
        filtered = [r for r in all_rows if abs(r["strike"] - spot) <= window]
        filtered.sort(key=lambda r: r["strike"])
        return filtered
    except Exception as e:
        print(f"[indiaopt] Fetch error: {e}")
        return None


# ============================================================
# MAIN CYCLE
# ============================================================
def fetch_and_store(url: str, key: str) -> bool:
    nifty, vix = fetch_nifty_and_vix()
    chain = fetch_option_chain(spot=nifty)

    if nifty is None and vix is None and chain is None:
        print("[auto_fetcher] All fetches failed.")
        return False

    record = {
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "nifty_spot": float(nifty) if nifty else None,
        "india_vix": float(vix) if vix else None,
        "chain_rows": len(chain) if chain else 0,
        "chain_json": chain if chain else [],
    }

    ok = supabase_insert(url, key, "live_data", record)
    if ok:
        print(f"[auto_fetcher] {now_ist():%H:%M:%S} | Nifty={nifty} | VIX={vix} | "
              f"Chain={len(chain) if chain else 0} rows")
    return ok


# ============================================================
# MAIN LOOP
# ============================================================
def run_loop(interval_sec: int = 300):
    url, key = _get_env()
    if not url or not key:
        print("[auto_fetcher] ERROR: set SUPABASE_URL and SUPABASE_KEY env vars")
        print(f"  SUPABASE_URL={url!r}")
        print(f"  SUPABASE_KEY={'***' if key else None}")
        return

    # DNS warm-up BEFORE any heavy imports
    if not ensure_dns(url):
        print("[auto_fetcher] Cannot resolve Supabase. Check network / URL.")
        return

    print(f"[auto_fetcher] Starting. Interval: {interval_sec}s. Ctrl+C to stop.")

    while True:
        try:
            fetch_and_store(url, key)
        except KeyboardInterrupt:
            print("\n[auto_fetcher] Stopped.")
            break
        except Exception as e:
            print(f"[auto_fetcher] Cycle error: {e}")
        time.sleep(interval_sec)


if __name__ == "__main__":
    run_loop(interval_sec=300)

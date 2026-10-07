"""
Autonomous Nifty Agent ? runs fetcher + agent in one loop.
Fetches NSE data every 5 min, runs agent, saves predictions to Supabase.
No browser needed.
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
from agent import NiftyAgent

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


def _get_env():
    url = os.environ.get("SUPABASE_URL", "").strip().strip('"').strip("'")
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")
    return url, key


def ensure_dns(url: str, max_attempts: int = 8) -> bool:
    host = url.replace("https://", "").replace("http://", "").split("/")[0]
    for attempt in range(1, max_attempts + 1):
        try:
            ip = socket.gethostbyname(host)
            print(f"[dns] OK: {host} -> {ip}")
            return True
        except Exception as e:
            print(f"[dns] attempt {attempt}/{max_attempts}: {e}")
            time.sleep(2)
    return False


# ============================================================
# SUPABASE ? direct HTTP
# ============================================================
def supabase_insert(url: str, key: str, table: str, record: dict) -> bool:
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


def supabase_update(url: str, key: str, table: str,
                    where: dict, values: dict) -> bool:
    """Update rows matching `where` with `values`. where={'col': val}"""
    params = "&".join(f"{k}=eq.{v}" for k, v in where.items())
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}?{params}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    try:
        r = requests.patch(endpoint, json=values, headers=headers, timeout=15)
        if r.status_code in (200, 204):
            return True
        print(f"[supabase] update HTTP {r.status_code}: {r.text[:150]}")
        return False
    except Exception as e:
        print(f"[supabase] update error: {e}")
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
        nifty = vix = None
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
        print(f"[fetch] Nifty/VIX error: {e}")
        return None, None


# ============================================================
# OPTION CHAIN ? cookie-aware NSE API
# ============================================================
class NSEOptionChainFetcher:
    HOME = "https://www.nseindia.com"
    DERIVATIVES = "https://www.nseindia.com/market-data/derivatives"
    API = "https://www.nseindia.com/api/option-chain-indices"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })
        self._last_cookie = 0

    def _handshake(self):
        try:
            self.session.get(self.HOME, timeout=15)
            time.sleep(0.5)
            self.session.get(self.DERIVATIVES, timeout=15)
            time.sleep(0.5)
            self._last_cookie = time.time()
            print("[nse] Cookie handshake complete")
        except Exception as e:
            print(f"[nse] Handshake failed: {e}")

    def fetch(self, symbol="NIFTY") -> Optional[pd.DataFrame]:
        if time.time() - self._last_cookie > 300:
            self._handshake()
        self.session.headers["Referer"] = self.DERIVATIVES
        try:
            r = self.session.get(self.API, params={"symbol": symbol}, timeout=15)
            if r.status_code != 200:
                print(f"[nse] HTTP {r.status_code}")
                self._last_cookie = 0
                return None
            if "json" not in r.headers.get("Content-Type", ""):
                self._last_cookie = 0
                return None
            data = r.json()
            if "records" not in data or "data" not in data["records"]:
                self._last_cookie = 0
                return None
            rows = []
            for rec in data["records"]["data"]:
                ce = rec.get("CE", {})
                pe = rec.get("PE", {})
                rows.append({
                    "strike": rec.get("strikePrice"),
                    "call_oi": ce.get("openInterest", 0),
                    "call_oi_change": ce.get("changeinOpenInterest", 0),
                    "call_ltp": ce.get("lastPrice", 0),
                    "call_iv": ce.get("impliedVolatility", 0),
                    "call_volume": ce.get("totalTradedVolume", 0),
                    "put_oi": pe.get("openInterest", 0),
                    "put_oi_change": pe.get("changeinOpenInterest", 0),
                    "put_ltp": pe.get("lastPrice", 0),
                    "put_iv": pe.get("impliedVolatility", 0),
                    "put_volume": pe.get("totalTradedVolume", 0),
                })
            return pd.DataFrame(rows).sort_values("strike").reset_index(drop=True)
        except Exception as e:
            print(f"[nse] Fetch error: {e}")
            self._last_cookie = 0
            return None


_nse_fetcher = NSEOptionChainFetcher()


def fetch_option_chain(spot=None) -> Optional[pd.DataFrame]:
    df = _nse_fetcher.fetch("NIFTY")
    if df is None or len(df) == 0:
        return None
    if spot and spot > 0:
        window = 500
        df = df[abs(df["strike"] - spot) <= window].reset_index(drop=True)
    return df


# ============================================================
# AGENT + STORAGE LOOP
# ============================================================
def _clean_features(feats: dict) -> dict:
    """Convert numpy types to Python native for JSON."""
    out = {}
    for k, v in feats.items():
        if isinstance(v, str):
            out[k] = v
        else:
            try:
                out[k] = float(v)
            except (ValueError, TypeError):
                out[k] = 0.0
    return out


def run_one_cycle(url: str, key: str, agent: NiftyAgent) -> bool:
    nifty, vix = fetch_nifty_and_vix()
    chain = fetch_option_chain(spot=nifty)

    # Save live_data
    chain_records = []
    if chain is not None and len(chain) > 0:
        chain_records = json.loads(chain.to_json(orient="records", default_handler=str))

    supabase_insert(url, key, "live_data", {
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "nifty_spot": float(nifty) if nifty else None,
        "india_vix": float(vix) if vix else None,
        "chain_rows": len(chain) if chain is not None else 0,
        "chain_json": chain_records,
    })

    # Run agent
    if chain is None or len(chain) == 0 or not nifty:
        print("[cycle] No chain or Nifty. Skipping agent.")
        return False

    # Label previous prediction with new spot
    if agent._pending is not None:
        try:
            realized_bps = (nifty - agent._pending["spot"]) / agent._pending["spot"] * 1e4
            label = 1 if realized_bps > 0 else 0
            supabase_update(url, key, "predictions",
                            where={"pred_ts": agent._pending["ts"]},
                            values={"outcome_bps": round(realized_bps, 3),
                                    "realized_label": label})
            print(f"[label] prev pred labeled: bps={realized_bps:.2f}, label={label}")
        except Exception as e:
            print(f"[label] error: {e}")
        agent._pending = None

    # New prediction
    try:
        agent.on_option_chain(chain, spot=nifty, vix=vix)
        pred = agent.predict()
    except Exception as e:
        print(f"[cycle] agent error: {e}")
        return False

    # Save prediction
    pred_record = {
        "pred_ts": float(pred.ts),
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "spot": float(pred.spot),
        "direction": str(pred.direction),
        "score": float(pred.score),
        "confidence": float(pred.confidence),
        "regime": str(pred.regime),
        "action": str(pred.action),
        "features": _clean_features(pred.features),
    }
    supabase_insert(url, key, "predictions", pred_record)

    # Print status
    vol = getattr(pred, "volatility", "?")
    print(f"[{now_ist():%H:%M:%S}] {pred.direction:8s} | conf={pred.confidence:5.1f}% | "
          f"vol={vol:8s} | {pred.action}")

    return True


def run_loop(interval_sec: int = 300):
    url, key = _get_env()
    if not url or not key:
        print("[startup] ERROR: set SUPABASE_URL and SUPABASE_KEY")
        return

    if not ensure_dns(url):
        print("[startup] DNS failed. Exiting.")
        return

    print("[startup] Initializing agent (loads ML model)...")
    try:
        agent = NiftyAgent()
        print("[startup] Agent ready.")
    except Exception as e:
        print(f"[startup] Agent init failed: {e}")
        return

    print(f"[startup] Starting autonomous loop. Interval: {interval_sec}s. Ctrl+C to stop.")

    while True:
        # Auto-stop at 3:15 PM IST
        now = now_ist()
        if now.hour == 15 and now.minute >= 15:
            print("[loop] 3:15 PM reached. Stopping before CAS window.")
            break
        if now.hour > 15:
            print("[loop] Past market hours. Stopping.")
            break

        try:
            run_one_cycle(url, key, agent)
        except KeyboardInterrupt:
            print("\n[loop] Stopped by user.")
            break
        except Exception as e:
            print(f"[loop] Cycle error: {e}")
        time.sleep(interval_sec)


if __name__ == "__main__":
    run_loop(interval_sec=300)

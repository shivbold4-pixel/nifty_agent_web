"""
Nifty Agent v2 ? Unified Fetcher + Agent + v4 Shadow Logger.

Single process replaces auto_fetcher.py + v4_shadow.py.
Runs every 5 minutes, logs:
  1. live_data (raw option chain + Nifty + VIX)
  2. predictions (v3 signal ? 9 features)
  3. predictions_v4 (candle features ? for future v4 training)

Auto-stops at 3:15 PM IST.
Includes 60-second heartbeat for suspension detection.
"""
import os
import sys
import time
import json
import socket
import threading
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta

from agent import NiftyAgent
from candle_features import compute_candle_features

IST = timezone(timedelta(hours=5, minutes=30))


def now_ist():
    return datetime.now(IST)


def _get_env():
    url = os.environ.get("SUPABASE_URL", "").strip().strip('"').strip("'")
    key = os.environ.get("SUPABASE_KEY", "").strip().strip('"').strip("'")
    return url, key


def ensure_dns(url):
    """Test connectivity by making an HTTP request."""
    for attempt in range(5):
        try:
            r = requests.get(f"{url.rstrip('/')}/rest/v1/", timeout=10)
            return True
        except Exception as e:
            print(f"[dns] attempt {attempt+1}/5: {str(e)[:60]}")
            time.sleep(3)
    return False


# ============================================================
# SUPABASE ? HTTP helpers
# ============================================================
def sb_insert(url, key, table, record):
    endpoint = f"{url.rstrip('/')}/rest/v1/{table}"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    for attempt in range(3):
        try:
            r = requests.post(endpoint, json=record, headers=headers, timeout=15)
            if r.status_code in (200, 201, 204):
                return True
            print(f"[supabase] HTTP {r.status_code}: {r.text[:150]}")
            return False
        except Exception as e:
            err = str(e)
            if "getaddrinfo" in err or "11001" in err:
                print(f"[supabase] DNS retry {attempt+1}/3")
                time.sleep(3)
            else:
                print(f"[supabase] error: {e}")
                return False
    return False


def sb_update(url, key, table, where, values):
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
        return r.status_code in (200, 204)
    except Exception as e:
        print(f"[supabase] update error: {e}")
        return False


# ============================================================
# NSE ? fetch Nifty, VIX, option chain
# ============================================================
def fetch_nifty_and_vix():
    try:
        from nselib import capital_market
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
        print(f"[nse] Nifty/VIX error: {e}")
        return None, None


def fetch_option_chain(spot=None):
    try:
        import asyncio
        from indiaopt import NSEClient

        async def _fetch():
            async with NSEClient() as nse:
                result = await nse.fetch_option_chain("NIFTY")
                rows = []
                for row in result.atm_window(n=200):
                    rows.append({
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
                return rows

        all_rows = asyncio.run(_fetch())
        if not all_rows:
            return None

        df = pd.DataFrame(all_rows)
        if spot and spot > 0:
            df = df[abs(df["strike"] - spot) <= 500].reset_index(drop=True)
        return df
    except Exception as e:
        print(f"[chain] error: {e}")
        return None


# ============================================================
# CANDLE FEATURES ? from in-memory price history
# ============================================================
def _build_candles_from_history(recent_spots, n=20):
    """Convert recent_spots deque to a candle DataFrame."""
    if not recent_spots or len(recent_spots) < 2:
        return None
    rows = list(recent_spots)[-n:]
    candles = []
    for i in range(1, len(rows)):
        prev = rows[i-1][1]
        cur = rows[i][1]
        if prev is None or cur is None:
            continue
        candles.append({
            "timestamp": datetime.fromtimestamp(rows[i][0], tz=IST),
            "open": float(prev),
            "high": float(max(prev, cur)),
            "low": float(min(prev, cur)),
            "close": float(cur),
            "volume": 0,
        })
    return pd.DataFrame(candles) if candles else None


# ============================================================
# MAIN LOOP
# ============================================================
def heartbeat(stop_event):
    """Print heartbeat every 60s ? detects process suspension."""
    while not stop_event.is_set():
        print(f"[v2] heartbeat | {now_ist():%H:%M:%S} IST")
        stop_event.wait(60)


def run_one_cycle(url, key, agent, v4_pending):
    # --- 1. Fetch NSE data ---
    nifty, vix = fetch_nifty_and_vix()
    chain = fetch_option_chain(spot=nifty)

    chain_records = []
    if chain is not None and len(chain) > 0:
        chain_records = json.loads(chain.to_json(orient="records", default_handler=str))

    # --- 2. Save live_data ---
    sb_insert(url, key, "live_data", {
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "nifty_spot": float(nifty) if nifty else None,
        "india_vix": float(vix) if vix else None,
        "chain_rows": len(chain) if chain is not None else 0,
        "chain_json": chain_records,
    })

    if chain is None or len(chain) == 0 or not nifty:
        print(f"[cycle] No chain or Nifty. Skipping.")
        return False

    # --- 3. Label previous v3 prediction ---
    if agent._pending is not None:
        try:
            realized_bps = (nifty - agent._pending["spot"]) / agent._pending["spot"] * 1e4


            # --- RISK MANAGER & CORRECT LABELING WIRE-UP ---
            direction = agent._pending.get("direction", "FLAT")
            points_moved = nifty - agent._pending["spot"]
            
            # 1. Correct labeling based on direction
            if direction == "BULLISH":
                label = 1 if realized_bps > 0 else 0
                mock_pnl = points_moved * 75 # Assuming 1 lot (75 qty)
            elif direction == "BEARISH":
                label = 1 if realized_bps < 0 else 0
                mock_pnl = -points_moved * 75
            else:
                label = 0
                mock_pnl = 0.0
            
            # 2. Feed the P&L to the Risk Manager
            if mock_pnl != 0.0:
                agent.risk.register_trade(mock_pnl)
            
            sb_update(url, key, "predictions",
                where={"pred_ts": agent._pending["ts"]},
                values={"outcome_bps": round(realized_bps, 3),
                        "realized_label": label})
        except Exception as e:
            print(f"[label v3] error: {e}")
        agent._pending = None

    # --- 4. Label previous v4 prediction ---
    if v4_pending.get("pred_ts") and v4_pending.get("spot"):
        try:
            realized_bps = (nifty - v4_pending["spot"]) / v4_pending["spot"] * 1e4
            sb_update(url, key, "predictions_v4",
                      where={"pred_ts": v4_pending["pred_ts"]},
                      values={"outcome_bps": round(realized_bps, 3),
                              "realized_label": 1 if realized_bps > 0 else 0})
        except Exception as e:
            print(f"[label v4] error: {e}")
    v4_pending.clear()

    # --- 5. Run v3 predict ---
    try:
        agent.on_option_chain(chain, spot=nifty, vix=vix)
        pred = agent.predict()
    except Exception as e:
        print(f"[cycle] agent error: {e}")
        return False

    # --- 6. Save v3 prediction ---
    def _clean(d):
        return {k: (float(v) if not isinstance(v, str) else v) for k, v in d.items()}

    sb_insert(url, key, "predictions", {
        "pred_ts": float(pred.ts),
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "spot": float(pred.spot),
        "direction": str(pred.direction),
        "score": float(pred.score),
        "confidence": float(pred.confidence),
        "regime": str(pred.regime),
        "action": str(pred.action),
        "features": _clean(pred.features),
    })

    # --- 7. Compute candle features + save v4 ---
    candle_feats = {}
    try:
        candles_df = _build_candles_from_history(agent.recent_spots, n=20)
        if candles_df is not None and len(candles_df) >= 5:
            candle_feats = compute_candle_features(candles_df)
    except Exception as e:
        print(f"[candle] error: {e}")

    v4_record = {
        "pred_ts": float(pred.ts),
        "ts_ist": now_ist().strftime("%Y-%m-%d %H:%M:%S"),
        "spot": float(pred.spot),
        "v3_direction": str(pred.direction),
        "v3_confidence": float(pred.confidence),
        "option_features": {
            "nifty_spot": float(nifty),
            "india_vix": float(vix) if vix else None,
            "chain_rows": len(chain),
        },
        "candle_features": candle_feats,
    }
    sb_insert(url, key, "predictions_v4", v4_record)
    v4_pending["pred_ts"] = float(pred.ts)
    v4_pending["spot"] = float(pred.spot)

    # --- 8. Log status line ---
    vol = getattr(pred, "volatility", "?")
    print(f"[{now_ist():%H:%M:%S}] v3={pred.direction:8s} | conf={pred.confidence:5.1f}% | "
          f"vol={vol:8s} | candles={len(candle_feats)} | {pred.action}")

    return True


def run_loop(interval_sec=300):
    url, key = _get_env()
    if not url or not key:
        print("[v2] ERROR: set SUPABASE_URL and SUPABASE_KEY")
        return

    if not ensure_dns(url):
        print("[v2] DNS failed. Exiting.")
        return

    print("[v2] Initializing agent...")
    try:
        agent = NiftyAgent()
        print("[v2] Agent ready.")
    except Exception as e:
        print(f"[v2] Agent init failed: {e}")
        return

    # Start heartbeat thread
    stop_event = threading.Event()
    hb_thread = threading.Thread(target=heartbeat, args=(stop_event,), daemon=True)
    hb_thread.start()

    print(f"[v2] Starting loop. Interval: {interval_sec}s. Ctrl+C to stop.")

    v4_pending = {}
    cycle_count = 0

    while True:
        now = now_ist()
        if now.hour == 15 and now.minute >= 15:
            print("[v2] 3:15 PM reached. Stopping before CAS window.")
            break
        if now.hour > 15:
            print("[v2] Past market hours. Stopping.")
            break

        try:
            run_one_cycle(url, key, agent, v4_pending)
            cycle_count += 1
        except KeyboardInterrupt:
            print("\n[v2] Stopped by user.")
            break
        except Exception as e:
            print(f"[v2] Cycle error: {e}")

        time.sleep(interval_sec)

    stop_event.set()
    print(f"[v2] Done. Total cycles: {cycle_count}")


if __name__ == "__main__":
    run_loop(interval_sec=300)
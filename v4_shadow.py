"""v4 Shadow Logger ? separate process, no impact on v3."""
import os, time, socket, requests, pandas as pd
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))
def now_ist(): return datetime.now(IST)

def _get_env():
    return (os.environ.get("SUPABASE_URL", "").strip().strip('"'),
            os.environ.get("SUPABASE_KEY", "").strip().strip('"'))

def ensure_dns(url):
    host = url.replace("https://", "").split("/")[0]
    for _ in range(5):
        try:
            socket.gethostbyname(host); return True
        except Exception: time.sleep(2)
    return False

def sb_insert(url, key, table, record):
    r = requests.post(f"{url.rstrip('/')}/rest/v1/{table}", json=record,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"}, timeout=15)
    return r.status_code in (200, 201, 204)

def sb_update(url, key, table, where, values):
    params = "&".join(f"{k}=eq.{v}" for k, v in where.items())
    r = requests.patch(f"{url.rstrip('/')}/rest/v1/{table}?{params}", json=values,
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Prefer": "return=minimal"}, timeout=15)
    return r.status_code in (200, 204)

def sb_get(url, key, path):
    r = requests.get(f"{url.rstrip('/')}/rest/v1/{path}",
        headers={"apikey": key, "Authorization": f"Bearer {key}"}, timeout=10)
    return r.json() if r.status_code == 200 else []

def fetch_recent_candles(url, key, n=20):
    rows = sb_get(url, key, f"live_data?order=id.desc&limit={n}")
    if not rows: return None
    rows = list(reversed(rows))
    candles = []
    for i in range(1, len(rows)):
        ps = rows[i-1].get("nifty_spot"); cs = rows[i].get("nifty_spot")
        if ps is None or cs is None: continue
        candles.append({"timestamp": pd.to_datetime(rows[i]["ts_ist"]),
                        "open": float(ps), "high": float(max(ps, cs)),
                        "low": float(min(ps, cs)), "close": float(cs), "volume": 0})
    return pd.DataFrame(candles) if candles else None

def run_loop(interval_sec=300):
    url, key = _get_env()
    if not url or not key:
        print("[v4] ERROR: set SUPABASE_URL and SUPABASE_KEY"); return
    if not ensure_dns(url):
        print("[v4] DNS failed. Exiting."); return
    from candle_features import compute_candle_features
    print(f"[v4] Shadow logger started. Interval: {interval_sec}s.")
    pending_ts = None; pending_spot = None
    while True:
        now = now_ist()
        if now.hour == 15 and now.minute >= 15:
            print("[v4] 3:15 PM reached. Stopping."); break
        if now.hour > 15:
            print("[v4] Past market hours. Stopping."); break
        try:
            live_rows = sb_get(url, key, "live_data?order=id.desc&limit=1")
            live = live_rows[0] if live_rows else None
            if live and pending_ts and pending_spot:
                cur = live.get("nifty_spot")
                if cur:
                    bps = (cur - pending_spot) / pending_spot * 1e4
                    sb_update(url, key, "predictions_v4",
                              {"pred_ts": pending_ts},
                              {"outcome_bps": round(bps, 3),
                               "realized_label": 1 if bps > 0 else 0})
                    print(f"[v4] {now:%H:%M:%S} labeled prev: bps={bps:.2f}")
            if live:
                candles = fetch_recent_candles(url, key, 20)
                cf = compute_candle_features(candles) if candles is not None else {}
                v3_rows = sb_get(url, key, "predictions?order=id.desc&limit=1")
                v3 = v3_rows[0] if v3_rows else None
                ts = time.time()
                sb_insert(url, key, "predictions_v4", {
                    "pred_ts": ts, "ts_ist": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "spot": float(live.get("nifty_spot", 0)),
                    "v3_direction": v3.get("direction") if v3 else None,
                    "v3_confidence": v3.get("confidence") if v3 else None,
                    "option_features": {"nifty_spot": live.get("nifty_spot"),
                                        "india_vix": live.get("india_vix"),
                                        "chain_rows": live.get("chain_rows")},
                    "candle_features": cf})
                pending_ts = ts; pending_spot = float(live.get("nifty_spot", 0))
                print(f"[v4] {now:%H:%M:%S} logged. v3={v3.get('direction') if v3 else 'N/A'} candles={len(cf)}")
        except Exception as e:
            print(f"[v4] cycle error: {e}")
        time.sleep(interval_sec)

if __name__ == "__main__":
    run_loop(interval_sec=300)

"""
Fetch FII/DII activity from NSE direct API, save to Supabase.
Uses cookie handshake (same technique as option chain fetch).
"""
import os, sys, time, socket
import requests
from datetime import datetime, timezone, timedelta

IST = timezone(timedelta(hours=5, minutes=30))


def _get_env():
    return (os.environ.get("SUPABASE_URL", "").strip().strip('"'),
            os.environ.get("SUPABASE_KEY", "").strip().strip('"'))


def ensure_dns(url):
    """Test connectivity by making an actual HTTP request, not just DNS lookup."""
    for attempt in range(5):
        try:
            r = requests.get(f"{url.rstrip('/')}/rest/v1/", timeout=10)
            # Any HTTP response means we reached Supabase
            return True
        except Exception as e:
            print(f"[dns] attempt {attempt+1}/5: {str(e)[:60]}")
            time.sleep(3)
    return False


def sb_insert(url, key, table, record):
    r = requests.post(
        f"{url.rstrip('/')}/rest/v1/{table}",
        json=record,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=15,
    )
    if r.status_code in (200, 201, 204):
        return True
    print(f"[supabase] HTTP {r.status_code}")
    print(f"[supabase] Response: {r.text[:500]}")
    return False


class NSEFIIFetcher:
    HOME = "https://www.nseindia.com"
    API = "https://www.nseindia.com/api/fiidiiTradeReact"

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                           "AppleWebKit/537.36 (KHTML, like Gecko) "
                           "Chrome/120.0.0.0 Safari/537.36"),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        })

    def _handshake(self):
        try:
            self.session.get(self.HOME, timeout=15)
            time.sleep(0.5)
            self.session.get(f"{self.HOME}/reports/fii-dii", timeout=15)
            time.sleep(0.5)
        except Exception as e:
            print(f"[nse] Handshake warning: {e}")

    def fetch(self):
        self._handshake()
        self.session.headers["Referer"] = f"{self.HOME}/reports/fii-dii"
        try:
            r = self.session.get(self.API, timeout=15)
            if r.status_code != 200:
                print(f"[nse] HTTP {r.status_code}")
                return None
            data = r.json()
            if not isinstance(data, list):
                print(f"[nse] Unexpected response type: {type(data)}")
                return None
            return data
        except Exception as e:
            print(f"[nse] Fetch error: {e}")
            return None


def _parse_number(s):
    if s is None: return 0.0
    try:
        return float(str(s).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _parse_date(s):
    """NSE returns dates like '13-Oct-2026'. Convert to ISO."""
    try:
        return datetime.strptime(s, "%d-%b-%Y").date().isoformat()
    except Exception:
        return datetime.now(IST).date().isoformat()


def main():
    url, key = _get_env()
    if not url or not key:
        print("[fii] ERROR: set SUPABASE_URL and SUPABASE_KEY"); sys.exit(1)
    if not ensure_dns(url):
        print("[fii] DNS failed"); sys.exit(1)

    print("[fii] Fetching FII/DII activity from NSE...")
    fetcher = NSEFIIFetcher()
    data = fetcher.fetch()

    if not data:
        print("[fii] No data returned"); sys.exit(1)

    print(f"[fii] Received {len(data)} categories")
    for item in data:
        print(f"  {item.get('category')}: {item.get('date')} "
              f"buy={item.get('buyValue')} sell={item.get('sellValue')} net={item.get('netValue')}")

    # Find FII and DII rows
    fii_row = next((x for x in data if "FII" in str(x.get("category", "")).upper()), None)
    dii_row = next((x for x in data if "DII" in str(x.get("category", "")).upper()), None)

    if not fii_row and not dii_row:
        print("[fii] Neither FII nor DII rows found"); sys.exit(1)

    trade_date = _parse_date((fii_row or dii_row).get("date", ""))
    fii_buy = _parse_number(fii_row.get("buyValue")) if fii_row else 0
    fii_sell = _parse_number(fii_row.get("sellValue")) if fii_row else 0
    fii_net = _parse_number(fii_row.get("netValue")) if fii_row else 0
    dii_buy = _parse_number(dii_row.get("buyValue")) if dii_row else 0
    dii_sell = _parse_number(dii_row.get("sellValue")) if dii_row else 0
    dii_net = _parse_number(dii_row.get("netValue")) if dii_row else 0

    record = {
        "trade_date": trade_date,
        "fii_buy": fii_buy,
        "fii_sell": fii_sell,
        "fii_net": fii_net,
        "dii_buy": dii_buy,
        "dii_sell": dii_sell,
        "dii_net": dii_net,
        "fii_dii_ratio": fii_net / max(abs(dii_net), 1),
    }

    if sb_insert(url, key, "daily_flows", record):
        print(f"\n[fii] Saved: {trade_date}")
        print(f"  FII net: {fii_net:+,.2f} Cr")
        print(f"  DII net: {dii_net:+,.2f} Cr")
    else:
        print("[fii] Save failed")


if __name__ == "__main__":
    main()

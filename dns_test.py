import requests
import socket

url = "https://cloudflare-dns.com/dns-query"
params = {"name": "ggznsiwxnjzmbzclrfy.supabase.co", "type": "A"}
headers = {"accept": "application/dns-json"}

print("Testing DNS-over-HTTPS (bypasses ISP DNS)...")
try:
    r = requests.get(url, params=params, headers=headers, timeout=10)
    data = r.json()
    print(f"Status: {data.get('Status')} (0=success, 3=NXDOMAIN)")
    if data.get("Answer"):
        for ans in data["Answer"]:
            print(f"  A record: {ans.get('data')}")
    else:
        print(f"  No answers. Full response: {data}")
except Exception as e:
    print(f"Error: {e}")

print("\nTesting with Google DNS-over-HTTPS...")
try:
    r = requests.get(
        "https://dns.google/resolve",
        params={"name": "ggznsiwxnjzmbzclrfy.supabase.co", "type": "A"},
        timeout=10
    )
    data = r.json()
    print(f"Status: {data.get('Status')}")
    if data.get("Answer"):
        for ans in data["Answer"]:
            print(f"  A record: {ans.get('data')}")
    else:
        print(f"  No answers. Full response: {data}")
except Exception as e:
    print(f"Error: {e}")

print("\nTesting direct HTTP request to Supabase...")
try:
    r = requests.get("https://ggznsiwxnjzmbzclrfy.supabase.co/rest/v1/", timeout=10)
    print(f"HTTP status: {r.status_code}")
    print(f"Response: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")

"""Hardcoded parser for NSE option chain CSV (nested CALLS/PUTS format)."""
import csv
import io
import pandas as pd


def _clean_numeric(s):
    s = s.astype(str).str.strip()
    s = s.replace({"-": None, "": None, "nan": None, "NaN": None,
                   "None": None, "null": None, "NULL": None})
    s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s, errors="coerce")


def parse_option_chain(file_or_df):
    # ---- Read raw text ----
    if isinstance(file_or_df, pd.DataFrame):
        return file_or_df.copy()

    try:
        file_or_df.seek(0)
    except Exception:
        pass

    raw_bytes = file_or_df.read()
    if not raw_bytes:
        raise ValueError("File is empty.")

    text = None
    for enc in ["utf-8-sig", "utf-8", "cp1252", "latin-1"]:
        try:
            text = raw_bytes.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        text = raw_bytes.decode("latin-1", errors="replace")

    # ---- Parse CSV ----
    rows = list(csv.reader(io.StringIO(text)))
    rows = [r for r in rows if any(str(c).strip() for c in r)]

    if len(rows) < 3:
        raise ValueError(f"Only {len(rows)} rows in file.")

    # ---- Detect nested NSE format ----
    header_top = [str(c).strip().upper() for c in rows[0]]
    header_mid = [str(c).strip().upper() for c in rows[1]]

    is_nested = any("CALLS" in c for c in header_top) or \
                any("PUTS" in c for c in header_top)

    if is_nested:
        # Find strike column position in header_mid
        strike_pos = None
        for i, h in enumerate(header_mid):
            if "STRIKE" in h:
                strike_pos = i
                break
        if strike_pos is None:
            raise ValueError(f"No STRIKE column. Headers: {header_mid}")

        data_rows = rows[2:]
        print(f"[parser] Nested format. Strike at column index {strike_pos}. "
              f"Data rows: {len(data_rows)}")

        # Field maps for CALLS side (left of strike)
        call_fields = ["call_oi", "call_oi_change", "call_volume", "call_iv",
                       "call_ltp", "call_change", "call_bid_qty", "call_bid",
                       "call_ask", "call_ask_qty"]

        # Field maps for PUTS side (right of strike)
        put_fields = ["put_bid_qty", "put_bid", "put_ask", "put_ask_qty",
                      "put_change", "put_ltp", "put_iv", "put_volume",
                      "put_oi_change", "put_oi"]

        # We assume NSE's exact layout: [empty, 10 call fields, strike, 10 put fields, empty]
        # Verify by position count
        n = strike_pos + 1 + len(put_fields) + 1  # +1 for trailing empty

        col_names = ["_skip"]
        col_names.extend(call_fields[:strike_pos - 1])
        col_names.append("strike")
        col_names.extend(put_fields)
        col_names.append("_trail")
        col_names = col_names[:n]

        # Pad/truncate rows to length n
        data_rows = [r + [""] * (n - len(r)) if len(r) < n else r[:n]
                     for r in data_rows]

        df = pd.DataFrame(data_rows, columns=col_names)
        df = df[[c for c in df.columns if not c.startswith("_")]]
    else:
        # Flat format: row 0 is header
        headers = [str(c).strip().lower().replace(" ", "_") for c in rows[0]]
        data_rows = rows[1:]
        n = len(headers)
        data_rows = [r + [""] * (n - len(r)) if len(r) < n else r[:n]
                     for r in data_rows]
        df = pd.DataFrame(data_rows, columns=headers)

    # ---- Clean numeric columns ----
    for c in df.columns:
        df[c] = _clean_numeric(df[c])

    # ---- Drop invalid strike rows ----
    if "strike" in df.columns:
        df = df.dropna(subset=["strike"]).reset_index(drop=True)

    if len(df) == 0:
        # Fallback: show what we have
        print(f"[parser] DEBUG columns: {list(df.columns)}")
        raise ValueError(
            f"Parsed 0 rows. Columns found: {list(df.columns)}. "
            f"Strike column present: {'strike' in df.columns}"
        )

    # ---- Ensure required columns exist ----
    required = ["strike", "call_oi", "put_oi", "call_ltp", "put_ltp"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing required columns: {missing}. "
            f"Available: {list(df.columns)}"
        )

    return df

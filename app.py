# Nifty Agent - Mobile Web UI (v2 with all fixes)
import time
import json
import io
from pathlib import Path
from datetime import datetime, timezone, timedelta

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.graph_objects as go

from agent import NiftyAgent
from parser_helper import parse_option_chain

# ---------- IST timezone ----------
IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

def ts_ist(ts_unix):
    return datetime.fromtimestamp(ts_unix, tz=IST)

# ---------- Page config ----------
st.set_page_config(page_title="Nifty Agent", page_icon="N", layout="centered",
                   initial_sidebar_state="collapsed")

# Auto-refresh every 60 seconds
st_autorefresh(interval=60000, key="auto_refresh")

st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1.0">
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .block-container { padding: 1rem !important; max-width: 720px !important; }
    .hero-card { background: #FFFFFF; border-radius: 16px; padding: 24px 20px; text-align: center; margin-bottom: 16px; border: 2px solid #E0E0E0; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
    .hero-bull { border: 2px solid #00A043; box-shadow: 0 0 24px rgba(0,160,67,0.20); }
    .hero-bear { border: 2px solid #D32F2F; box-shadow: 0 0 24px rgba(211,47,47,0.20); }
    .hero-flat { border: 2px solid #F57C00; box-shadow: 0 0 24px rgba(245,124,0,0.20); }
    .hero-direction { font-size: 2.2rem; font-weight: 800; margin: 0; line-height: 1.1; color: #1A1A1A; }
    .hero-sub { font-size: 0.9rem; opacity: 0.7; margin-top: 8px; color: #666; }
    .hero-spot { font-size: 1.3rem; font-weight: 600; opacity: 0.9; margin-top: 4px; color: #1A1A1A; }
    .plan-card { background: #F9F9F9; border-radius: 12px; padding: 16px; margin: 12px 0; border-left: 4px solid #00A043; }
    .plan-card.bear { border-left-color: #D32F2F; }
    .plan-card.flat { border-left-color: #F57C00; }
    .plan-title { font-weight: 700; font-size: 1.05rem; margin-bottom: 10px; color: #1A1A1A; }
    .plan-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.92rem; border-bottom: 1px solid #E0E0E0; }
    .plan-row:last-child { border-bottom: none; }
    .plan-label { opacity: 0.7; color: #555; }
    .plan-value { font-weight: 600; color: #1A1A1A; }
    #MainMenu {visibility: hidden;} footer {visibility: hidden;} header {visibility: hidden;}
</style>
""", unsafe_allow_html=True)


def check_password():
    try:
        correct = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        correct = None
    if not correct:
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.markdown("### Nifty Agent")
    pw = st.text_input("Password", type="password", key="pw_input")
    if st.button("Unlock", use_container_width=True):
        if pw == correct:
            st.session_state.auth_ok = True
            st.rerun()
        else:
            st.error("Wrong password")
    return False


if not check_password():
    st.stop()

if "agent" not in st.session_state:
    try:
        sb_url = st.secrets.get("SUPABASE_URL", None)
        sb_key = st.secrets.get("SUPABASE_KEY", None)
    except Exception:
        sb_url, sb_key = None, None
    st.session_state.agent = NiftyAgent(supabase_url=sb_url, supabase_key=sb_key)
    st.session_state.history = []
    st.session_state.last_pred = None
    st.session_state.uploaded_seen = set()
    st.session_state.df = None
    st.session_state._last_pred_ts = 0.0

agent = st.session_state.agent

st.markdown("<h1 style='text-align:center; margin-bottom:0; font-size:1.6rem;'>Nifty Agent</h1>"
            "<p style='text-align:center; opacity:0.6; font-size:0.85rem; margin-top:4px;'>"
            "Upload option chain to get next-minute bias</p>", unsafe_allow_html=True)

# ============================================================
# AUTO-FETCH FROM SUPABASE live_data
# ============================================================
auto_data_used = False
auto_ts_display = "-"
auto_nifty = None
auto_vix = None
auto_chain_rows = 0

try:
    if agent.cloud is not None:
        _latest = (agent.cloud.client.table("live_data")
                   .select("*")
                   .order("created_at", desc=True)
                   .limit(1)
                   .execute())
        if _latest.data:
            _row = _latest.data[0]
            _fp = f"auto:{_row.get('created_at','')}"
            auto_ts_display = _row.get("ts_ist", "?")
            auto_nifty = _row.get("nifty_spot")
            auto_vix = _row.get("india_vix")
            _chain = _row.get("chain_json") or []
            auto_chain_rows = len(_chain)

            if _fp not in st.session_state.uploaded_seen and _chain:
                _df_auto = pd.DataFrame(_chain)
                for _c in _df_auto.columns:
                    if _df_auto[_c].dtype == object:
                        _df_auto[_c] = pd.to_numeric(
                            _df_auto[_c].astype(str).str.replace(",", ""),
                            errors="coerce"
                        )
                _df_auto = _df_auto.dropna(subset=["strike"]).reset_index(drop=True)
                if len(_df_auto) > 0:
                    agent.on_option_chain(_df_auto, spot=auto_nifty, vix=auto_vix)
                    _pred = agent.predict()
                    st.session_state.last_pred = _pred
                    st.session_state.df = _df_auto
                    st.session_state.uploaded_seen.add(_fp)
                    st.session_state.last_auto_ts = auto_ts_display
                    st.session_state.history.append({
                        "time": now_ist().strftime("%H:%M:%S"),
                        "spot": round(_pred.spot, 1),
                        "direction": _pred.direction,
                        "score": _pred.score,
                        "confidence": _pred.confidence,
                        "regime": _pred.regime,
                        "action": _pred.action,
                    })
                    auto_data_used = True
except Exception as _e:
    print(f"[app] auto-fetch error: {_e}")

if auto_data_used:
    st.success(f"LIVE auto-data | Nifty {auto_nifty} | VIX {auto_vix} | "
               f"{auto_chain_rows} strikes | fetched {auto_ts_display} IST")
elif auto_ts_display != "-":
    st.info(f"Cached data from {auto_ts_display} IST. "
            f"Upload CSV to refresh, or wait for next fetcher cycle.")
else:
    st.warning("No auto-data yet. Run `python auto_fetcher.py` or upload CSV below.")

# ============================================================

with st.expander("Settings", expanded=False):
    st.info("Tip: Set spot BEFORE uploading the CSV")
    spot_override = st.number_input("Actual Spot Price (0 = auto-detect from ATM)",
                                     min_value=0.0, value=0.0, step=1.0)
    vix = st.slider("India VIX", 8.0, 40.0, 14.0, 0.1)
    auto_label = st.checkbox("Auto-learn from previous prediction", value=True)

uploaded = st.file_uploader("Upload option chain", type=None,
                             help="Any CSV or Excel file. On mobile, tap Browse and select your file.")

if uploaded is not None:
    fingerprint = f"{uploaded.name}:{uploaded.size}"
    if fingerprint not in st.session_state.uploaded_seen:
        with st.spinner("Analyzing..."):
            try:
                file_bytes = uploaded.read()
            except Exception as e:
                st.error(f"Could not read file: {e}")
                st.stop()

            if not file_bytes:
                st.error("File is empty.")
                st.stop()

            try:
                df = parse_option_chain(io.BytesIO(file_bytes))
            except Exception as e:
                st.error(f"Could not parse file: {e}")
                st.stop()

            if df is None or len(df) == 0:
                st.error("File parsed but contains no rows.")
                st.stop()

            if "strike" not in df.columns:
                st.error(f"No 'strike' column found. Columns: {list(df.columns)}")
                st.stop()

            # Auto-label previous prediction
            try:
                if auto_label and st.session_state.last_pred is not None:
                    if "call_ltp" in df.columns and "put_ltp" in df.columns:
                        diff = (df.call_ltp - df.put_ltp).abs()
                        spot_now = float(df.loc[diff.idxmin(), "strike"])
                        if pd.notna(spot_now):
                            agent.label_previous(spot_now)
            except Exception:
                pass

            # Predict
            try:
                spot_arg = spot_override if spot_override > 0 else None
                agent.on_option_chain(df, spot=spot_arg, vix=vix)
                pred = agent.predict()
            except Exception as e:
                st.error(f"Prediction failed: {e}")
                st.stop()

            st.session_state.last_pred = pred
            st.session_state.uploaded_seen.add(fingerprint)
            st.session_state.df = df

            # ---- Guard against duplicate log entries ----
            # Only log if this is genuinely a new prediction (not a Streamlit rerun)
            is_new_prediction = abs(pred.ts - st.session_state._last_pred_ts) > 1.0

            if is_new_prediction:
                st.session_state._last_pred_ts = pred.ts
                st.session_state.history.append({
                    "time": ts_ist(pred.ts).strftime("%H:%M:%S"),
                    "spot": round(pred.spot, 1),
                    "direction": pred.direction,
                    "score": pred.score,
                    "confidence": pred.confidence,
                    "regime": pred.regime,
                    "action": pred.action,
                })

                # Log to disk
                try:
                    log_path = Path("logs") / f"predictions_{now_ist():%Y%m%d}.jsonl"
                    log_path.parent.mkdir(exist_ok=True)
                    with open(log_path, "a") as f:
                        f.write(json.dumps({
                            "ts": pred.ts,
                            "ts_ist": ts_ist(pred.ts).strftime("%Y-%m-%d %H:%M:%S"),
                            "spot": pred.spot,
                            "direction": pred.direction,
                            "score": pred.score,
                            "confidence": pred.confidence,
                            "regime": pred.regime,
                            "action": pred.action,
                            "stop": pred.stop_loss,
                            "target": pred.take_profit,
                            "contributions": pred.contributions,
                        }) + "\n")
                except Exception:
                    pass

# ---------- Render prediction ----------
pred = st.session_state.last_pred
if pred is not None:
    dir_class = {"BULLISH": "hero-bull", "BEARISH": "hero-bear"}.get(pred.direction, "hero-flat")

    st.markdown(f"""<div class="hero-card {dir_class}">
        <p class="hero-direction">{pred.direction}</p>
        <p class="hero-spot">Spot {pred.spot:.1f}</p>
        <p class="hero-sub">Score {pred.score:+.2f} &middot; {pred.regime} regime</p>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"**Confidence: {pred.confidence}%**")
    try:
        conf_int = int(pred.confidence) if not (pred.confidence is None or str(pred.confidence) == "nan") else 0
        st.progress(min(max(conf_int, 0), 100))
    except Exception:
        st.progress(0)

    plan_class = "plan-card"
    if pred.direction == "BEARISH":
        plan_class += " bear"
    elif pred.direction == "FLAT":
        plan_class += " flat"

    if pred.action.startswith(("BUY", "SELL")):
        st.markdown(f"""<div class="{plan_class}">
            <div class="plan-title">{pred.action}</div>
            <div class="plan-row"><span class="plan-label">Entry</span><span class="plan-value">{pred.spot:.1f}</span></div>
            <div class="plan-row"><span class="plan-label">Stop loss</span><span class="plan-value" style="color:#D32F2F;">{pred.stop_loss}</span></div>
            <div class="plan-row"><span class="plan-label">Target</span><span class="plan-value" style="color:#00A043;">{pred.take_profit}</span></div>
            <div class="plan-row"><span class="plan-label">Expected move</span><span class="plan-value">+/-{pred.expected_points} pts</span></div>
            <div class="plan-row"><span class="plan-label">Size multiplier</span><span class="plan-value">x{pred.size_mult}</span></div>
        </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f"""<div class="{plan_class}">
            <div class="plan-title">{pred.action}</div>
            <div class="plan-row"><span class="plan-label">Reason</span><span class="plan-value">Low conviction or panic regime</span></div>
        </div>""", unsafe_allow_html=True)

    with st.expander("Layer contributions", expanded=False):
        contrib = pred.contributions
        cc = pd.DataFrame({"Layer": list(contrib.keys()), "Score": list(contrib.values())})
        fig = go.Figure(go.Bar(x=cc["Score"], y=cc["Layer"], orientation="h",
                               marker=dict(color=["#00A043" if v > 0.05 else "#D32F2F" if v < -0.05 else "#999" for v in cc["Score"]])))
        fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis=dict(range=[-1, 1], showgrid=False), yaxis=dict(showgrid=False),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#1A1A1A"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Parsed data preview (first 5 rows)", expanded=False):
        if st.session_state.df is not None:
            st.dataframe(st.session_state.df.head(5), use_container_width=True, hide_index=True)
            st.caption(f"Parsed {len(st.session_state.df)} rows, {len(st.session_state.df.columns)} columns")
        else:
            st.info("Upload a file to see the preview.")

if st.session_state.history:
    st.markdown("---")
    st.markdown("### Session History (IST)")
    hist_df = pd.DataFrame(st.session_state.history[::-1])
    st.dataframe(hist_df[["time", "spot", "direction", "confidence", "action"]],
                 use_container_width=True, hide_index=True)

st.markdown("---")
if st.button("Save Model to Cloud"):
    if agent.cloud is not None:
        agent.force_save_model()
        st.success("Model saved to Supabase.")
    else:
        st.warning("Cloud not configured.")

if st.button("Retrain from History"):
    if agent.cloud is not None:
        with st.spinner("Retraining..."):
            result = agent.retrain()
        st.json(result)
    else:
        st.warning("Cloud not configured.")

st.markdown(f"<p style='text-align:center; opacity:0.4; font-size:0.75rem;'>Nifty Agent - {len(st.session_state.history)} predictions &middot; {now_ist().strftime('%Y-%m-%d %H:%M IST')}</p>", unsafe_allow_html=True)

"""
Nifty Agent ? Read-only display app.
Reads latest predictions and live_data from Supabase.
No agent logic here ? the autonomous fetcher handles everything.
"""
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import streamlit as st
from streamlit_autorefresh import st_autorefresh
import pandas as pd
import plotly.graph_objects as go
from supabase import create_client

IST = timezone(timedelta(hours=5, minutes=30))

def now_ist():
    return datetime.now(IST)

st.set_page_config(page_title="Nifty Agent", page_icon="N",
                   layout="centered", initial_sidebar_state="collapsed")

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


# ============================================================
# CONNECT TO SUPABASE
# ============================================================
try:
    sb_url = st.secrets.get("SUPABASE_URL", None)
    sb_key = st.secrets.get("SUPABASE_KEY", None)
except Exception:
    sb_url, sb_key = None, None

if not sb_url or not sb_key:
    st.error("Supabase credentials missing in secrets.")
    st.stop()

@st.cache_resource
def get_client(url, key):
    return create_client(url, key)

client = get_client(sb_url, sb_key)


# ============================================================
# FETCH LATEST
# ============================================================
def fetch_latest_pred():
    try:
        r = client.table("predictions").select("*").order("id", desc=True).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception as e:
        print(f"[app] fetch error: {e}")
        return None


def fetch_latest_live():
    try:
        r = client.table("live_data").select("*").order("id", desc=True).limit(1).execute()
        return r.data[0] if r.data else None
    except Exception:
        return None


def fetch_recent_preds(limit=20):
    try:
        r = client.table("predictions").select(
            "ts_ist,spot,direction,confidence,action"
        ).order("id", desc=True).limit(limit).execute()
        return r.data or []
    except Exception:
        return []


pred = fetch_latest_pred()
live = fetch_latest_live()
recent = fetch_recent_preds(20)


# ============================================================
# DISPLAY
# ============================================================
st.markdown("<h1 style='text-align:center; margin-bottom:0; font-size:1.6rem;'>Nifty Agent</h1>"
            "<p style='text-align:center; opacity:0.6; font-size:0.85rem; margin-top:4px;'>"
            "Autonomous live signals</p>", unsafe_allow_html=True)

# Status banner
if live:
    age_min = (now_ist() - datetime.strptime(
        live.get("ts_ist", ""), "%Y-%m-%d %H:%M:%S"
    ).replace(tzinfo=IST)).total_seconds() / 60 if live.get("ts_ist") else 999
    if age_min < 7:
        st.success(f"LIVE | Nifty {live.get('nifty_spot')} | VIX {live.get('india_vix')} | "
                   f"{live.get('chain_rows')} strikes | {live.get('ts_ist')} IST")
    elif age_min < 30:
        st.info(f"Delayed ({age_min:.0f}m ago) | Nifty {live.get('nifty_spot')} | "
                f"{live.get('ts_ist')} IST")
    else:
        st.warning(f"Stale ({age_min:.0f}m ago) ? is the fetcher running?")
else:
    st.warning("No data yet. Start the fetcher on your PC.")

# Signal card
if pred:
    dir_class = {"BULLISH": "hero-bull", "BEARISH": "hero-bear"}.get(pred["direction"], "hero-flat")
    st.markdown(f"""<div class="hero-card {dir_class}">
        <p class="hero-direction">{pred["direction"]}</p>
        <p class="hero-spot">Spot {pred["spot"]:.1f}</p>
        <p class="hero-sub">Score {pred["score"]:+.2f} &middot; {pred["regime"]} regime</p>
    </div>""", unsafe_allow_html=True)

    st.markdown(f"**Confidence: {pred['confidence']}%**")
    st.progress(min(int(pred["confidence"]), 100))

    # Volatility + regime from features
    feats = pred.get("features") or {}
    vol_conf = feats.get("vol_conf", 0)
    regime = feats.get("regime", "UNKNOWN")

    col1, col2 = st.columns(2)
    with col1:
        if vol_conf and vol_conf > 60:
            st.success(f"HIGH VOLATILITY ({vol_conf}%)")
        elif vol_conf:
            st.info(f"LOW VOLATILITY ({vol_conf}%)")
        else:
            st.info("Volatility: N/A")
    with col2:
        st.markdown(f"**Regime:** {regime}")

    # Action card
    plan_class = "plan-card"
    if pred["direction"] == "BEARISH":
        plan_class += " bear"
    elif pred["direction"] == "FLAT":
        plan_class += " flat"

    st.markdown(f"""<div class="{plan_class}">
        <div class="plan-title">{pred["action"]}</div>
        <div class="plan-row"><span class="plan-label">Time</span><span class="plan-value">{pred["ts_ist"]} IST</span></div>
        <div class="plan-row"><span class="plan-label">Spot</span><span class="plan-value">{pred["spot"]:.1f}</span></div>
        <div class="plan-row"><span class="plan-label">Direction</span><span class="plan-value">{pred["direction"]}</span></div>
        <div class="plan-row"><span class="plan-label">Confidence</span><span class="plan-value">{pred["confidence"]}%</span></div>
    </div>""", unsafe_allow_html=True)

    with st.expander("Layer contributions", expanded=False):
        numeric = {k: v for k, v in feats.items()
                   if isinstance(v, (int, float)) and not isinstance(v, bool)}
        if numeric:
            cc = pd.DataFrame({"Layer": list(numeric.keys()),
                               "Score": list(numeric.values())})
            fig = go.Figure(go.Bar(x=cc["Score"], y=cc["Layer"], orientation="h",
                                   marker=dict(color=[
                                       "#00A043" if v > 0.05 else "#D32F2F" if v < -0.05 else "#999"
                                       for v in cc["Score"]])))
            fig.update_layout(height=280, margin=dict(l=0, r=0, t=10, b=0),
                              xaxis=dict(range=[-1, 1], showgrid=False),
                              yaxis=dict(showgrid=False),
                              plot_bgcolor="rgba(0,0,0,0)",
                              paper_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#1A1A1A"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

# Recent predictions
if recent:
    st.markdown("---")
    st.markdown("### Recent predictions (IST)")
    hist_df = pd.DataFrame(recent)
    st.dataframe(hist_df, use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown(f"<p style='text-align:center; opacity:0.4; font-size:0.75rem;'>"
            f"Read-only view | Data from autonomous fetcher | "
            f"Auto-refresh in 60s</p>", unsafe_allow_html=True)

# Auto-refresh handled by st_autorefresh at top

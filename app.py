# Nifty Agent - Mobile Web UI
import time
import json
import io
from pathlib import Path
from datetime import datetime
from urllib.parse import quote

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from agent import NiftyAgent
from parser_helper import parse_option_chain

st.set_page_config(page_title="Nifty Agent", page_icon="N", layout="centered",
                   initial_sidebar_state="collapsed")

st.markdown("""
<meta name="viewport" content="width=device-width, initial-scale=1.0">
""", unsafe_allow_html=True)

st.markdown("""
<style>
    .block-container { padding: 1rem !important; max-width: 720px !important; }
    .hero-card { background: #1A1D24; border-radius: 16px; padding: 24px 20px; text-align: center; margin-bottom: 16px; border: 1px solid #2A2D34; }
    .hero-bull { border: 2px solid #00C853; box-shadow: 0 0 24px rgba(0,200,83,0.15); }
    .hero-bear { border: 2px solid #FF1744; box-shadow: 0 0 24px rgba(255,23,68,0.15); }
    .hero-flat { border: 2px solid #FFB300; box-shadow: 0 0 24px rgba(255,179,0,0.15); }
    .hero-direction { font-size: 2.2rem; font-weight: 800; margin: 0; line-height: 1.1; }
    .hero-sub { font-size: 0.9rem; opacity: 0.7; margin-top: 8px; }
    .hero-spot { font-size: 1.3rem; font-weight: 600; opacity: 0.9; margin-top: 4px; }
    .plan-card { background: #1A1D24; border-radius: 12px; padding: 16px; margin: 12px 0; border-left: 4px solid #00C853; }
    .plan-card.bear { border-left-color: #FF1744; }
    .plan-card.flat { border-left-color: #FFB300; }
    .plan-title { font-weight: 700; font-size: 1.05rem; margin-bottom: 10px; }
    .plan-row { display: flex; justify-content: space-between; padding: 6px 0; font-size: 0.92rem; border-bottom: 1px solid #2A2D34; }
    .plan-row:last-child { border-bottom: none; }
    .plan-label { opacity: 0.6; }
    .plan-value { font-weight: 600; }
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
    st.session_state.agent = NiftyAgent()
    st.session_state.history = []
    st.session_state.last_pred = None
    st.session_state.uploaded_seen = set()
    st.session_state.df = None

agent = st.session_state.agent

st.markdown("<h1 style='text-align:center; margin-bottom:0; font-size:1.6rem;'>Nifty Agent</h1>"
            "<p style='text-align:center; opacity:0.6; font-size:0.85rem; margin-top:4px;'>"
            "Upload option chain to get next-minute bias</p>", unsafe_allow_html=True)

with st.expander("Settings", expanded=False):
    spot_override = st.number_input("Actual Spot Price (0 = auto-detect from ATM)",
                                     min_value=0.0, value=0.0, step=1.0)
    vix = st.slider("India VIX", 8.0, 40.0, 14.0, 0.1)
    auto_label = st.checkbox("Auto-learn from previous prediction", value=True)

uploaded = st.file_uploader("Upload option chain", type=None,
                             help="Any CSV or Excel file. On mobile, tap Browse and select your file.")

if uploaded is not None:
    fingerprint = f"{uploaded.name}:{uploaded.size}:{spot_override}"
    if fingerprint not in st.session_state.uploaded_seen:
        with st.spinner("Analyzing..."):
            # Read file bytes once
            try:
                file_bytes = uploaded.read()
            except Exception as e:
                st.error(f"Could not read file: {e}")
                st.stop()

            if not file_bytes:
                st.error("File is empty.")
                st.stop()

            # Parse
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

            st.session_state.history.append({
                "time": datetime.fromtimestamp(pred.ts).strftime("%H:%M:%S"),
                "spot": round(pred.spot, 1),
                "direction": pred.direction,
                "score": pred.score,
                "confidence": pred.confidence,
                "regime": pred.regime,
                "action": pred.action,
            })

            # Log
            try:
                log_path = Path("logs") / f"predictions_{datetime.now():%Y%m%d}.jsonl"
                log_path.parent.mkdir(exist_ok=True)
                with open(log_path, "a") as f:
                    f.write(json.dumps({
                        "ts": pred.ts, "spot": pred.spot,
                        "direction": pred.direction, "score": pred.score,
                        "confidence": pred.confidence, "regime": pred.regime,
                        "action": pred.action,
                        "stop": pred.stop_loss, "target": pred.take_profit,
                        "contributions": pred.contributions,
                    }) + "\n")
            except Exception:
                pass

# ---- Render ----
pred = st.session_state.last_pred
if pred is not None:
    dir_class = {"BULLISH": "hero-bull", "BEARISH": "hero-bear"}.get(pred.direction, "hero-flat")
    dir_emoji = {"BULLISH": "BULL", "BEARISH": "BEAR"}.get(pred.direction, "FLAT")
    st.markdown(f"""<div class="hero-card {dir_class}">
        <p class="hero-direction">{dir_emoji} {pred.direction}</p>
        <p class="hero-spot">Spot {pred.spot:.1f}</p>
        <p class="hero-sub">Score {pred.score:+.2f} &middot; {pred.regime} regime</p>
    </div>""", unsafe_allow_html=True)
    st.markdown(f"**Confidence: {pred.confidence}%**")
    st.progress(min(int(pred.confidence), 100))

    plan_class = "plan-card"
    if pred.direction == "BEARISH":
        plan_class += " bear"
    elif pred.direction == "FLAT":
        plan_class += " flat"

    if pred.action.startswith(("BUY", "SELL")):
        st.markdown(f"""<div class="{plan_class}">
            <div class="plan-title">{pred.action}</div>
            <div class="plan-row"><span class="plan-label">Entry</span><span class="plan-value">{pred.spot:.1f}</span></div>
            <div class="plan-row"><span class="plan-label">Stop loss</span><span class="plan-value" style="color:#FF1744;">{pred.stop_loss}</span></div>
            <div class="plan-row"><span class="plan-label">Target</span><span class="plan-value" style="color:#00C853;">{pred.take_profit}</span></div>
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
                               marker=dict(color=["#00C853" if v > 0.05 else "#FF1744" if v < -0.05 else "#666" for v in cc["Score"]])))
        fig.update_layout(height=200, margin=dict(l=0, r=0, t=10, b=0),
                          xaxis=dict(range=[-1, 1], showgrid=False), yaxis=dict(showgrid=False),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", font=dict(color="#FAFAFA"))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with st.expander("Parsed data preview (first 5 rows)", expanded=False):
        if st.session_state.df is not None:
            st.dataframe(st.session_state.df.head(5), use_container_width=True, hide_index=True)
            st.caption(f"Parsed {len(st.session_state.df)} rows, {len(st.session_state.df.columns)} columns")
        else:
            st.info("Upload a file to see the preview.")

if st.session_state.history:
    st.markdown("---")
    st.markdown("### Session History")
    hist_df = pd.DataFrame(st.session_state.history[::-1])
    st.dataframe(hist_df[["time", "spot", "direction", "confidence", "action"]],
                 use_container_width=True, hide_index=True)

st.markdown("---")
st.markdown(f"<p style='text-align:center; opacity:0.4; font-size:0.75rem;'>Nifty Agent - {len(st.session_state.history)} predictions</p>", unsafe_allow_html=True)

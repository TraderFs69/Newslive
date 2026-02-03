import streamlit as st
import requests
import pandas as pd
import os
import time
import json
from datetime import datetime, timezone
from dotenv import load_dotenv
from openai import OpenAI

# =====================
# CONFIG
# =====================
st.set_page_config(layout="wide", page_title="🚨 Social News — Trader Actif")
st.title("🚨 Social News Scanner — Trader Actif")

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_URL")

REFRESH_SEC = 60
WINDOW_SEC = 300

# =====================
# WATCHLIST
# =====================
DEFAULT_WATCHLIST = (
    "SPY,QQQ,IWM,VIXY,IBIT,FBTC,"
    "NVDA,TSLA,AMD,META,SMCI,COIN,MARA,PLTR"
)

watchlist = st.sidebar.text_area(
    "Watchlist (séparée par des virgules)",
    DEFAULT_WATCHLIST
)

tickers = [t.strip().upper() for t in watchlist.split(",") if t.strip()]

# =====================
# GROUPS
# =====================
ETF_INDEX = {"SPY", "QQQ", "IWM"}
VIX_ETF = {"VIXY"}
CRYPTO_ETF = {"IBIT", "FBTC"}
ACTIONS = set(tickers) - ETF_INDEX - VIX_ETF - CRYPTO_ETF

THRESHOLDS = {
    "ACTION": 12,
    "ETF": 40,
    "VIX": 25,
    "CRYPTO": 20
}

# =====================
# STOCKTWITS
# =====================
def fetch_stocktwits(symbol):
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
        r = requests.get(url, timeout=10)
        return r.json().get("messages", [])
    except:
        return []

def recent_messages(messages):
    now = datetime.now(timezone.utc)
    return [
        m for m in messages
        if (now - datetime.fromisoformat(m["created_at"].replace("Z", ""))).seconds < WINDOW_SEC
    ]

# =====================
# LLM
# =====================
LLM_PROMPT = """
You are an active stock trader.
Explain why people are talking about this right now.

Return ONLY JSON with:
bias (Bull/Bear/Neutral),
tradeable (Yes/No),
horizon (Intraday/Swing),
risk (short),
summary (max 20 words).
"""

def llm_analyze(text):
    try:
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Active trader"},
                {"role": "user", "content": LLM_PROMPT + "\n" + text}
            ],
            temperature=0.2
        )
        return json.loads(res.choices[0].message.content)
    except:
        return None

# =====================
# DISCORD
# =====================
def send_discord(symbol, llm, count):
    if not DISCORD_WEBHOOK:
        return

    color = 3066993 if llm["bias"] == "Bull" else 15158332
    payload = {
        "embeds": [{
            "title": f"🚨 SOCIAL SPIKE — {symbol}",
            "color": color,
            "fields": [
                {"name": "Messages (5 min)", "value": str(count), "inline": True},
                {"name": "Bias", "value": llm["bias"], "inline": True},
                {"name": "Horizon", "value": llm["horizon"], "inline": True},
                {"name": "Risk", "value": llm["risk"], "inline": False},
                {"name": "Summary", "value": llm["summary"], "inline": False}
            ],
            "footer": {"text": "Social News Scanner"}
        }]
    }
    requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)

# =====================
# SESSION ANTI-SPAM
# =====================
if "sent" not in st.session_state:
    st.session_state.sent = set()

# =====================
# MAIN LOOP
# =====================
st.subheader("📡 Live Social Signals")

for symbol in tickers:
    messages = fetch_stocktwits(symbol)
    recent = recent_messages(messages)
    count = len(recent)

    if symbol in ETF_INDEX:
        threshold, group = THRESHOLDS["ETF"], "ETF"
    elif symbol in VIX_ETF:
        threshold, group = THRESHOLDS["VIX"], "VIX"
    elif symbol in CRYPTO_ETF:
        threshold, group = THRESHOLDS["CRYPTO"], "CRYPTO"
    else:
        threshold, group = THRESHOLDS["ACTION"], "ACTION"

    if count >= threshold:
        st.markdown(f"### 🔥 {symbol} — {count} messages / 5 min")

        if group == "ACTION":
            text = " ".join(m["body"] for m in recent[:20])
            llm = llm_analyze(text)

            if llm:
                st.caption(
                    f"🧠 {llm['bias']} | Tradeable: {llm['tradeable']} | {llm['horizon']}"
                )
                st.write(llm["summary"])

                key = f"{symbol}_{recent[0]['id']}"
                if llm["tradeable"] == "Yes" and key not in st.session_state.sent:
                    send_discord(symbol, llm, count)
                    st.session_state.sent.add(key)
        else:
            st.caption("🌐 Macro sentiment (no alert)")

        st.divider()

# =====================
# AUTO REFRESH
# =====================
time.sleep(REFRESH_SEC)
st.rerun()

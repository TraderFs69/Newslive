import streamlit as st
import requests
import os
import time
import json
from datetime import datetime, timezone
from openai import OpenAI

# =====================================================
# UTILITAIRE SECRETS (local + Streamlit Cloud)
# =====================================================
def get_secret(key):
    return st.secrets.get(key, os.getenv(key))

OPENAI_API_KEY = get_secret("OPENAI_API_KEY")
DISCORD_WEBHOOK = get_secret("DISCORD_WEBHOOK_URL")

client = OpenAI(api_key=OPENAI_API_KEY)

# =====================================================
# CONFIG GÉNÉRALE
# =====================================================
st.set_page_config(
    page_title="🚨 Social News Trader",
    layout="wide"
)

st.title("🚨 Social News Scanner — Trader Actif")
st.caption("StockTwits live • Social spikes • LLM context • Discord alerts")

REFRESH_SEC = 60        # rafraîchissement
WINDOW_SEC = 300        # fenêtre 5 minutes

# =====================================================
# WATCHLIST
# =====================================================
DEFAULT_WATCHLIST = (
    "SPY,QQQ,IWM,VIXY,IBIT,FBTC,"
    "NVDA,TSLA,AMD,META,SMCI,COIN,MARA,PLTR"
)

watchlist_text = st.sidebar.text_area(
    "📋 Watchlist (séparée par des virgules)",
    DEFAULT_WATCHLIST,
    height=120
)

tickers = [t.strip().upper() for t in watchlist_text.split(",") if t.strip()]

# =====================================================
# GROUPES & SEUILS
# =====================================================
ETF_INDEX = {"SPY", "QQQ", "IWM"}
VIX_ETF = {"VIXY"}
CRYPTO_ETF = {"IBIT", "FBTC"}

THRESHOLDS = {
    "ACTION": 12,
    "ETF": 40,
    "VIX": 25,
    "CRYPTO": 20
}

# =====================================================
# STOCKTWITS
# =====================================================
def fetch_stocktwits(symbol):
    try:
        url = f"https://api.stocktwits.com/api/2/streams/symbol/{symbol}.json"
        r = requests.get(url, timeout=10)
        return r.json().get("messages", [])
    except:
        return []

def recent_messages(messages):
    now = datetime.now(timezone.utc)
    recent = []
    for m in messages:
        try:
            created = datetime.fromisoformat(
                m["created_at"].replace("Z", "")
            )
            if (now - created).seconds < WINDOW_SEC:
                recent.append(m)
        except:
            pass
    return recent

# =====================================================
# LLM OPENAI (SEULEMENT SI UTILE)
# =====================================================
LLM_PROMPT = """
You are an active stock trader.
Explain why people are talking about this right now.

Return ONLY valid JSON with:
bias (Bull/Bear/Neutral),
tradeable (Yes/No),
horizon (Intraday/Swing),
risk (one short sentence),
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

# =====================================================
# DISCORD
# =====================================================
def send_discord_alert(symbol, llm, count):
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
                {"name": "Summary", "value": llm["summary"], "inline": False},
            ],
            "footer": {"text": "Social News Scanner — Trader Actif"}
        }]
    }

    requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)

# =====================================================
# ANTI-SPAM SESSION
# =====================================================
if "sent_alerts" not in st.session_state:
    st.session_state.sent_alerts = set()

# =====================================================
# MAIN
# =====================================================
st.subheader("📡 Social Signals Live")

for symbol in tickers:

    messages = fetch_stocktwits(symbol)
    recent = recent_messages(messages)
    count = len(recent)

    if symbol in ETF_INDEX:
        group = "ETF"
        threshold = THRESHOLDS["ETF"]
    elif symbol in VIX_ETF:
        group = "VIX"
        threshold = THRESHOLDS["VIX"]
    elif symbol in CRYPTO_ETF:
        group = "CRYPTO"
        threshold = THRESHOLDS["CRYPTO"]
    else:
        group = "ACTION"
        threshold = THRESHOLDS["ACTION"]

    if count >= threshold:

        st.markdown(f"### 🔥 {symbol} — {count} messages / 5 min")

        # ======================
        # ACTIONS → LLM + DISCORD
        # ======================
        if group == "ACTION":
            text = " ".join(m["body"] for m in recent[:20])
            llm = llm_analyze(text)

            if llm:
                st.caption(
                    f"🧠 {llm['bias']} | Tradeable: {llm['tradeable']} | {llm['horizon']}"
                )
                st.write(llm["summary"])

                alert_id = f"{symbol}_{recent[0]['id']}"

                if (
                    llm["tradeable"] == "Yes"
                    and alert_id not in st.session_state.sent_alerts
                ):
                    send_discord_alert(symbol, llm, count)
                    st.session_state.sent_alerts.add(alert_id)

        # ======================
        # ETF / VIX / CRYPTO → CONTEXTE SEULEMENT
        # ======================
        else:
            st.caption("🌐 Macro sentiment — no Discord alert")

        st.divider()

# =====================================================
# AUTO REFRESH
# =====================================================
time.sleep(REFRESH_SEC)
st.rerun()

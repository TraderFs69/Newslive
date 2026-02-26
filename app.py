import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from streamlit_autorefresh import st_autorefresh
from collections import Counter

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

st.set_page_config(layout="wide")
st_autorefresh(interval=60000, key="refresh")

POLYGON_KEY = st.secrets.get("POLYGON_API_KEY")
DISCORD_WEBHOOK = st.secrets.get("DISCORD_WEBHOOK")

if not POLYGON_KEY:
    st.error("POLYGON_API_KEY manquante.")
    st.stop()

MAX_AGE_MINUTES = 15

# -------------------------------------------------
# BLOOMBERG CLASSIC STYLE
# -------------------------------------------------

st.markdown("""
<style>
html, body, [class*="css"] {
    background-color: #000000 !important;
    color: #ffffff !important;
    font-family: monospace !important;
}
.bloom-header {
    font-size: 18px;
    font-weight: bold;
    color: #ff9900;
    padding-bottom: 8px;
    border-bottom: 1px solid #222222;
    margin-bottom: 15px;
}
section[data-testid="stSidebar"] {
    background-color: #050505 !important;
    border-right: 1px solid #222222;
}
[data-testid="metric-container"] {
    background-color: #0d0d0d;
    border: 1px solid #222222;
    padding: 10px;
    border-radius: 4px;
}
.news-card {
    background-color: #0d0d0d;
    padding: 14px;
    margin-bottom: 8px;
    border-bottom: 1px solid #222222;
}
.ticker {
    color: #ff9900;
    font-weight: bold;
}
.time {
    color: #aaaaaa;
    font-size: 12px;
}
.title {
    color: #ffffff;
    font-size: 14px;
}
.badge {
    color: #ff9900;
    font-size: 12px;
}
a {
    color: #ff9900;
    text-decoration: none;
}
hr {
    border: 0;
    height: 1px;
    background: #222222;
}
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="bloom-header">TEA <NEWS> RUSSELL 3000 – ULTRA LIVE</div>', unsafe_allow_html=True)

# -------------------------------------------------
# INIT STATE
# -------------------------------------------------

if "sent_ids" not in st.session_state:
    st.session_state.sent_ids = set()

if "feed" not in st.session_state:
    st.session_state.feed = []

# -------------------------------------------------
# LOAD RUSSELL
# -------------------------------------------------

@st.cache_data
def load_russell():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return set(df["Symbol"].tolist())

russell_set = load_russell()

# -------------------------------------------------
# SCORING FUNCTION
# -------------------------------------------------

def catalyst_label(title):
    t = title.lower()
    if "earnings" in t or "guidance" in t:
        return "EARNINGS"
    elif "merger" in t or "acquisition" in t or "fda" in t:
        return "MAJOR EVENT"
    elif "upgrade" in t or "downgrade" in t or "analyst" in t:
        return "ANALYST"
    else:
        return "NEWS"

# -------------------------------------------------
# FETCH NEWS
# -------------------------------------------------

url = f"https://api.polygon.io/v2/reference/news?limit=50&apiKey={POLYGON_KEY}"
response = requests.get(url, timeout=10)
data = response.json()

now = datetime.now(timezone.utc)

for article in data.get("results", []):

    article_id = article.get("id")
    if not article_id:
        continue

    if article_id in st.session_state.sent_ids:
        continue

    try:
        published = datetime.fromisoformat(
            article["published_utc"].replace("Z", "+00:00")
        )
    except:
        continue

    # ULTRA LIVE FILTER
    if now - published > timedelta(minutes=MAX_AGE_MINUTES):
        continue

    for ticker in article.get("tickers", []):
        if ticker in russell_set:

            label = catalyst_label(article["title"])

            news_item = {
                "ticker": ticker,
                "title": article["title"],
                "time": published,
                "url": article["article_url"],
                "label": label
            }

            st.session_state.feed.insert(0, news_item)
            st.session_state.feed = st.session_state.feed[:100]
            st.session_state.sent_ids.add(article_id)

            if DISCORD_WEBHOOK:
                payload = {
                    "content": f"🚨 {ticker} {label}\n{article['title']}\n{article['article_url']}"
                }
                try:
                    requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
                except:
                    pass

            break

# -------------------------------------------------
# DISPLAY
# -------------------------------------------------

col1, col2 = st.columns([3,1])

def time_ago(dt):
    delta = datetime.now(timezone.utc) - dt
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds//60}m"
    else:
        return f"{seconds//3600}h"

with col1:
    for item in st.session_state.feed:
        st.markdown(f"""
        <div class="news-card">
            <div class="ticker">{item['ticker']}</div>
            <div class="time">{time_ago(item['time'])} ago</div>
            <div class="title">{item['title']}</div>
            <div class="badge">{item['label']}</div>
            <a href="{item['url']}" target="_blank">OPEN</a>
        </div>
        """, unsafe_allow_html=True)

with col2:

    st.markdown("### TERMINAL")

    st.metric("ACTIVE CATALYSTS", len(st.session_state.feed))

    ticker_counts = Counter([x["ticker"] for x in st.session_state.feed])
    top = ticker_counts.most_common(5)

    st.markdown("#### MOST ACTIVE")
    for t, c in top:
        st.write(f"{t} : {c}")

    st.markdown("#### LAST UPDATE")
    st.write(now.strftime("%H:%M:%S UTC"))

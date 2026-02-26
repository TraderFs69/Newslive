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
# STYLE FULL BLACK TERMINAL
# -------------------------------------------------

st.markdown("""
<style>
html, body, [class*="css"] {
    background-color: #000000 !important;
    color: white !important;
}
.news-card {
    background-color: #111111;
    padding: 18px;
    border-radius: 16px;
    margin-bottom: 15px;
    border: 1px solid #222222;
}
.ticker {
    font-weight: bold;
    font-size: 18px;
    color: #1d9bf0;
}
.time {
    font-size: 12px;
    color: #888888;
}
.title {
    font-size: 16px;
    color: white;
}
.badge-red { color: #ff4d4d; font-weight:bold;}
.badge-orange { color: #ff9900; font-weight:bold;}
.badge-yellow { color: #ffcc00; font-weight:bold;}
a { color: #1d9bf0; text-decoration:none;}
</style>
""", unsafe_allow_html=True)

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
# SCORING
# -------------------------------------------------

def catalyst_score(title):
    title_lower = title.lower()

    if any(w in title_lower for w in ["earnings", "guidance"]):
        return 3, "EARNINGS"
    elif any(w in title_lower for w in ["merger", "acquisition", "fda"]):
        return 2, "MAJOR EVENT"
    elif any(w in title_lower for w in ["upgrade", "downgrade", "analyst"]):
        return 1, "ANALYST"
    else:
        return 0, "NEWS"

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

    # 🔥 ULTRA LIVE FILTER (≤ 15 minutes)
    if now - published > timedelta(minutes=MAX_AGE_MINUTES):
        continue

    for ticker in article.get("tickers", []):
        if ticker in russell_set:

            score, label = catalyst_score(article["title"])

            news_item = {
                "ticker": ticker,
                "title": article["title"],
                "time": published,
                "url": article["article_url"],
                "score": score,
                "label": label
            }

            st.session_state.feed.insert(0, news_item)
            st.session_state.feed = st.session_state.feed[:100]
            st.session_state.sent_ids.add(article_id)

            if DISCORD_WEBHOOK:
                payload = {
                    "content": f"🚨 **{ticker} {label}**\n{article['title']}\n{article['article_url']}"
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
    elif seconds < 600:
        return f"{seconds//60}m"
    else:
        return f"{seconds//3600}h"

with col1:

    for item in st.session_state.feed:

        age_seconds = (now - item["time"]).total_seconds()

        if age_seconds < 300:
            badge_class = "badge-red"
        elif age_seconds < 900:
            badge_class = "badge-orange"
        else:
            badge_class = "badge-yellow"

        st.markdown(f"""
        <div class="news-card">
            <div class="ticker">${item['ticker']}</div>
            <div class="time">{time_ago(item['time'])} ago</div>
            <div class="title">{item['title']}</div>
            <div class="{badge_class}">{item['label']}</div>
            <br>
            <a href="{item['url']}" target="_blank">View Article</a>
        </div>
        """, unsafe_allow_html=True)

with col2:

    st.markdown("### 📊 Ultra Live Terminal")

    st.metric("Active Catalysts", len(st.session_state.feed))

    ticker_counts = Counter([x["ticker"] for x in st.session_state.feed])
    top = ticker_counts.most_common(5)

    st.markdown("#### 🔥 Most Active")
    for t, c in top:
        st.write(f"{t} : {c}")

    st.markdown("#### ⏱ Last Update")
    st.write(now.strftime("%H:%M:%S UTC"))

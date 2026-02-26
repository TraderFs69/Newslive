import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone

st.set_page_config(layout="wide")
st.title("⚡ TEA – News Catalyst Engine")

POLYGON_KEY = st.secrets["POLYGON_API_KEY"]
DISCORD_WEBHOOK = st.secrets["DISCORD_WEBHOOK"]

st.experimental_autorefresh(interval=60000)

# ---- INIT TIMESTAMP ----
if "last_timestamp" not in st.session_state:
    st.session_state.last_timestamp = None

# ---- LOAD RUSSELL ----
df = pd.read_excel("russell3000_constituents.xlsx")
russell_set = set(df["Symbol"].tolist())

# ---- POLYGON CALL ----
url = f"https://api.polygon.io/v2/reference/news?limit=100&apiKey={POLYGON_KEY}"
r = requests.get(url)
data = r.json()

new_hits = []

for article in data.get("results", []):

    published = datetime.fromisoformat(article["published_utc"].replace("Z","+00:00"))

    # 🔥 Skip si déjà vu
    if st.session_state.last_timestamp and published <= st.session_state.last_timestamp:
        continue

    for ticker in article.get("tickers", []):
        if ticker in russell_set:

            new_hits.append({
                "ticker": ticker,
                "title": article["title"],
                "time": published,
                "url": article["article_url"]
            })

            # Discord
            payload = {
                "content": f"🚨 **{ticker} Breaking News**\n{article['title']}\n{article['article_url']}"
            }
            requests.post(DISCORD_WEBHOOK, json=payload)

            break

# ---- UPDATE TIMESTAMP ----
if data.get("results"):
    latest_time = max(
        datetime.fromisoformat(a["published_utc"].replace("Z","+00:00"))
        for a in data["results"]
    )
    st.session_state.last_timestamp = latest_time

# ---- DISPLAY ----
if not new_hits:
    st.success("Aucun nouveau catalyst.")
else:
    st.error(f"🔥 {len(new_hits)} nouveaux catalysts")

    for hit in new_hits:
        st.markdown("---")
        st.subheader(f"{hit['ticker']} 🚨")
        st.write(hit["title"])
        st.write(hit["time"])
        st.markdown(hit["url"])

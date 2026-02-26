import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from streamlit_autorefresh import st_autorefresh

# -------------------------------------------------
# CONFIG
# -------------------------------------------------

st.set_page_config(layout="wide")
st.title("⚡ TEA – News Catalyst Engine")

# Auto refresh every 60 seconds
st_autorefresh(interval=60000, key="news_refresh")

# Load secrets safely
POLYGON_KEY = st.secrets.get("POLYGON_API_KEY")
DISCORD_WEBHOOK = st.secrets.get("DISCORD_WEBHOOK")

if not POLYGON_KEY:
    st.error("POLYGON_API_KEY manquante dans Secrets.")
    st.stop()

# -------------------------------------------------
# INITIALISATION MÉMOIRE
# -------------------------------------------------

if "last_timestamp" not in st.session_state:
    st.session_state.last_timestamp = None

if "sent_ids" not in st.session_state:
    st.session_state.sent_ids = set()

# -------------------------------------------------
# LOAD RUSSELL 3000
# -------------------------------------------------

@st.cache_data
def load_russell():
    df = pd.read_excel("russell3000_constituents.xlsx")
    return set(df["Symbol"].tolist())

russell_set = load_russell()

# -------------------------------------------------
# FETCH POLYGON NEWS
# -------------------------------------------------

try:
    url = f"https://api.polygon.io/v2/reference/news?limit=100&apiKey={POLYGON_KEY}"
    response = requests.get(url, timeout=10)
    data = response.json()
except Exception as e:
    st.error("Erreur API Polygon")
    st.stop()

new_hits = []

for article in data.get("results", []):

    article_id = article.get("id")
    if not article_id:
        continue

    # Skip si déjà traité
    if article_id in st.session_state.sent_ids:
        continue

    try:
        published = datetime.fromisoformat(
            article["published_utc"].replace("Z", "+00:00")
        )
    except:
        continue

    # Skip si plus ancien que dernier timestamp
    if st.session_state.last_timestamp and published <= st.session_state.last_timestamp:
        continue

    mentioned = article.get("tickers", [])

    for ticker in mentioned:
        if ticker in russell_set:

            hit = {
                "ticker": ticker,
                "title": article["title"],
                "time": published,
                "url": article["article_url"]
            }

            new_hits.append(hit)

            # Marquer comme envoyé
            st.session_state.sent_ids.add(article_id)

            # Discord (si activé)
            if DISCORD_WEBHOOK:
                payload = {
                    "content": f"🚨 **{ticker} Breaking News**\n{article['title']}\n{article['article_url']}"
                }
                try:
                    requests.post(DISCORD_WEBHOOK, json=payload, timeout=5)
                except:
                    pass

            break

# -------------------------------------------------
# UPDATE TIMESTAMP
# -------------------------------------------------

if data.get("results"):
    try:
        latest_time = max(
            datetime.fromisoformat(a["published_utc"].replace("Z", "+00:00"))
            for a in data["results"]
        )
        st.session_state.last_timestamp = latest_time
    except:
        pass

# -------------------------------------------------
# DISPLAY
# -------------------------------------------------

if not new_hits:
    st.success("Aucun nouveau catalyst.")
else:
    st.error(f"🔥 {len(new_hits)} nouveaux catalysts détectés")

    for hit in new_hits:
        st.markdown("---")
        st.subheader(f"{hit['ticker']} 🚨")
        st.write(hit["title"])
        st.write(hit["time"])
        st.markdown(hit["url"])

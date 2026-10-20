import streamlit as st
from PIL import Image
import psycopg2
import os
from urllib.parse import urlparse
import requests

st.set_page_config(
    page_title="Sports Card Catalog",
    page_icon="🏟️",
    layout="wide"
)

# Hide Streamlit menu/footer + center images on mobile
st.markdown("""
    <style>
    .stDeployButton, div[data-testid="stToolbar"], footer {display: none !important;}
    
    /* Center images on mobile */
    @media (max-width: 768px) {
        div[data-testid="stImage"] {
            display: flex !important;
            justify-content: center !important;
        }
        div[data-testid="stImage"] img {
            margin: 0 auto !important;
        }
    }
    </style>
""", unsafe_allow_html=True)

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        result = urlparse(database_url)
        return psycopg2.connect(
            dbname=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port,
            sslmode="require"
        )
    st.error("DATABASE_URL not found")
    st.stop()

@st.cache_data(ttl=120)
def get_distinct_years():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT year FROM sports_cards WHERE year IS NOT NULL ORDER BY year DESC")
        years = [str(row[0]) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return years
    except:
        return []

@st.cache_data(ttl=120)
def get_distinct_sets(year=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if year and year != "All Years":
            cur.execute(
                "SELECT DISTINCT set_name FROM sports_cards WHERE year = %s AND set_name IS NOT NULL ORDER BY set_name",
                (year,)
            )
        else:
            cur.execute("SELECT DISTINCT set_name FROM sports_cards WHERE set_name IS NOT NULL ORDER BY set_name")
        sets = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return sets
    except:
        return []

@st.cache_data(ttl=120)
def get_distinct_players(year=None, set_name=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        query = "SELECT DISTINCT player FROM sports_cards WHERE player IS NOT NULL"
        params = []
        if year and year != "All Years":
            query += " AND year = %s"
            params.append(year)
        if set_name and set_name != "All Sets":
            query += " AND set_name = %s"
            params.append(set_name)
        query += " ORDER BY player"
        cur.execute(query, params)
        players = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return players
    except:
        return []

@st.cache_data(ttl=60)
def get_cards(year=None, set_name=None, player=None, card_number=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT id, card_name, player, year, set_name, card_number,
                   brand_detail, image_url, qty_available, orientation
            FROM sports_cards
            WHERE 1=1
        """
        params = []

        if year and year != "All Years":
            query += " AND year = %s"
            params.append(year)
        if set_name and set_name != "All Sets":
            query += " AND set_name = %s"
            params.append(set_name)
        if player and player != "All Players":
            query += " AND player = %s"
            params.append(player)
        if card_number and card_number.strip():
            query += " AND card_number = %s"
            params.append(card_number.strip())

        # Sort by set_name ascending, then player, then card_number
        query += " ORDER BY set_name ASC, player ASC, card_number ASC"

        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Error loading cards: {e}")
        return []

# ===================== CATALOG UI =====================
st.title("🏟️ Sports Card Catalog")
st.caption("Browse the collection")

# Filters
col1, col2, col3, col4 = st.columns(4)

with col1:
    years = ["All Years"] + get_distinct_years()
    selected_year = st.selectbox("Year", years)

with col2:
    sets = ["All Sets"] + get_distinct_sets(selected_year)
    selected_set = st.selectbox("Set / Brand", sets)

with col3:
    players = ["All Players"] + get_distinct_players(selected_year, selected_set)
    selected_player = st.selectbox("Player", players)

with col4:
    card_number_filter = st.text_input("Card #", placeholder="Optional")

if st.button("🔍 Search Cards", type="primary"):
    st.session_state.catalog_cards = get_cards(
        selected_year, selected_set, selected_player, card_number_filter
    )

if "catalog_cards" in st.session_state:
    cards = st.session_state.catalog_cards
    st.success(f"Showing **{len(cards)}** card(s)")

    # Display in a nice grid
    cols_per_row = 4
    for i in range(0, len(cards), cols_per_row):
        cols = st.columns(cols_per_row)
        for j, col in enumerate(cols):
            if i + j < len(cards):
                card = cards[i + j]
                (card_id, card_name, player, year, set_name,
                 card_number, brand_detail, image_url, qty, orientation) = card

                current_orientation = orientation if orientation is not None else 90

                with col:
                    if image_url:
                        try:
                            response = requests.get(image_url, stream=True, timeout=8)
                            img = Image.open(response.raw).convert("RGB")
                            rotated = img.rotate(current_orientation, expand=True)
                            st.image(rotated, use_container_width=True)
                        except:
                            st.image(image_url, use_container_width=True)
                    else:
                        st.write("No image")

                    st.markdown(f"**{player}**")
                    st.caption(f"{year} {set_name} #{card_number}")
                    if brand_detail:
                        st.caption(brand_detail)
                    st.caption(f"Qty: {qty}")
else:
    st.info("Use the filters above and click **Search Cards** to browse the collection.")

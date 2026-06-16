import streamlit as st
from PIL import Image
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from io import BytesIO
from sentence_transformers import SentenceTransformer
import requests

st.set_page_config(page_title="Sports Card Scanner", layout="centered")

# Hide Streamlit UI elements
st.markdown("""
    <style>
    .stDeployButton, div[data-testid="stToolbar"], footer {display: none !important;}
    .stImage img {border-radius: 8px;}
    </style>
""", unsafe_allow_html=True)

# ------------------ CONFIG ------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

@st.cache_resource
def load_model():
    return SentenceTransformer('clip-ViT-B-32')

model = load_model()

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        result = urlparse(database_url)
        return psycopg2.connect(
            dbname=result.path[1:], user=result.username, password=result.password,
            host=result.hostname, port=result.port, sslmode="require"
        )
    st.error("DATABASE_URL not found")
    st.stop()

# ------------------ FORCE PORTRAIT HTML ------------------
def display_portrait_image(image_url, caption, key=None):
    """Display image forced as portrait using HTML"""
    html = f"""
    <div style="text-align: center; margin-bottom: 10px;">
        <p style="margin-bottom: 5px; font-size: 14px;">{caption}</p>
        <img src="{image_url}" 
             style="width: 300px; max-width: 300px; height: auto; border-radius: 12px; 
                    object-fit: contain; transform: rotate(0deg);"
             alt="{caption}">
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner")
st.caption("Powered by CLIP AI • Tap +1 to increase quantity")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if 'results' not in st.session_state:
    st.session_state.results = None
if 'processed' not in st.session_state:
    st.session_state.processed = False

if uploaded_file:
    # Display uploaded image in portrait
    img = Image.open(uploaded_file).convert('RGB')
    if img.width > img.height:
        img = img.rotate(180, expand=True)
    st.image(img, caption="Your Scanned Card", width=300)

    if st.button("🔍 Process with AI", type="primary", use_container_width=True):
        with st.spinner("AI analyzing card..."):
            embedding = model.encode(img).tolist()

            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT id, card_name, image_url, embedding <=> %s::vector AS distance
                FROM sports_cards 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector 
                LIMIT 6
            """, (embedding, embedding))
            st.session_state.results = cur.fetchall()
            cur.close()
            conn.close()
            st.session_state.processed = True

    if st.session_state.processed and st.session_state.results:
        st.write("### Tap **+1** to increase quantity")

        for row in st.session_state.results:
            card_id = row[0]
            card_name = row[1]
            image_url = row[2]
            similarity = round((1 - row[3]) * 100, 1)

            if image_url:
                display_portrait_image(image_url, f"{card_name} ({similarity}%)")

                col1, col2 = st.columns([4, 1])
                with col2:
                    if st.button("＋1", key=f"add_{card_id}"):
                        new_qty, name = increment_qty(card_id)
                        if new_qty is not None:
                            st.success(f"✅ {name} → **{new_qty}**")
                            st.rerun()

        st.divider()

        # Save as New Card
        st.subheader("🆕 Save as New Card")
        col1, col2 = st.columns(2)
        with col1:
            player_new = st.selectbox("Player Name", get_players(), key="new_player")
            year_new = st.number_input("Year", 1900, 2026, 2023, key="new_year")
        with col2:
            brand_new = st.selectbox("Set / Brand", get_brands(), key="new_set")
        
        if st.button("Save as New Card + Upload Image", type="secondary", use_container_width=True):
            with st.spinner("Saving..."):
                new_id = save_as_new_card(Image.open(uploaded_file).convert('RGB'), player_new, year_new, brand_new)
                if new_id:
                    st.success(f"✅ New card saved! ID: {new_id}")
                    st.balloons()

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

# ------------------ PORTRAIT HTML DISPLAY ------------------
def display_portrait_image(image_url, caption, similarity=None):
    """Force portrait using HTML - best chance on iPhone Safari"""
    full_caption = f"{caption} ({similarity}%)" if similarity else caption
    st.markdown(f"""
        <div style="text-align: center; margin: 15px 0;">
            <p style="margin-bottom: 8px; font-size: 15px;">{full_caption}</p>
            <img src="{image_url}" 
                 style="width: 300px; 
                        max-width: 300px; 
                        height: auto; 
                        border-radius: 12px; 
                        box-shadow: 0 4px 8px rgba(0,0,0,0.1);"
                 alt="{full_caption}">
        </div>
    """, unsafe_allow_html=True)

# ------------------ HELPERS ------------------
def get_embedding(image):
    return model.encode(image).tolist()

def increment_qty(card_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE sports_cards 
            SET qty_available = COALESCE(qty_available, 0) + 1 
            WHERE id = %s
            RETURNING qty_available, card_name;
        """, (card_id,))
        result = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()
        return result[0], result[1]
    except Exception as e:
        st.error(f"Error: {e}")
        return None, None

def save_as_new_card(pil_image, player, year, set_name):
    # ... (keep your existing function)
    pass   # I'll add it if needed

# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")
st.caption("Powered by CLIP AI • Tap +1 to increase quantity")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if 'results' not in st.session_state:
    st.session_state.results = None
if 'processed' not in st.session_state:
    st.session_state.processed = False

if uploaded_file:
    st.image(uploaded_file, caption="Your Scanned Card", width=300)

    if st.button("🔍 Process with AI", type="primary", use_container_width=True):
        with st.spinner("AI analyzing..."):
            pil_image = Image.open(uploaded_file).convert('RGB')
            embedding = get_embedding(pil_image)

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
        st.write("### Tap **+1** below the image to increase quantity")

        for row in st.session_state.results:
            card_id = row[0]
            card_name = row[1]
            image_url = row[2]
            similarity = round((1 - row[3]) * 100, 1)

            if image_url:
                display_portrait_image(image_url, card_name, similarity)

                col1, col2 = st.columns([3, 1])
                with col2:
                    if st.button("＋1", key=f"add_{card_id}"):
                        new_qty, name = increment_qty(card_id)
                        if new_qty is not None:
                            st.success(f"✅ {name} → **{new_qty}**")
                            st.rerun()

        st.divider()

        # Save as New Card section here...

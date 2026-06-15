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

st.set_page_config(page_title="Sports Card Scanner", layout="centered")

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

# ------------------ DROPDOWNS ------------------
@st.cache_data(ttl=300)
def get_players():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT player_name FROM cards_players ORDER BY player_name")
        players = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return players or ["Unknown"]
    except:
        return ["Unknown"]

@st.cache_data(ttl=300)
def get_brands():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT brand_name FROM cards_brands ORDER BY brand_name")
        brands = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return brands or ["Unknown"]
    except:
        return ["Unknown"]

# ------------------ HELPERS ------------------
def get_embedding(image):
    return model.encode(image).tolist()

def upload_to_cloudinary(pil_image, public_id=None):
    try:
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)
        result = cloudinary.uploader.unsigned_upload(
            buffer, upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),
            folder="sports_cards", public_id=public_id, resource_type="image"
        )
        return result.get("secure_url")
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def increment_qty(card_id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE sports_cards 
            SET qty_available = COALESCE(qty_available, 0) + 1 
            WHERE id = %s
            RETURNING qty_available;
        """, (card_id,))
        new_qty = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_qty
    except Exception as e:
        st.error(f"Error updating quantity: {e}")
        return None

def save_as_new_card(pil_image, player, year, set_name):
    try:
        card_name = f"{player} - {set_name} ({year})"
        image_url = upload_to_cloudinary(pil_image, public_id=f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        embedding = get_embedding(pil_image)
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player, year, set_name, condition, image_url, embedding, scanned_at, qty_available)
            VALUES (%s, %s, %s, %s, %s, %s, %s::vector, %s, 1) RETURNING id;
        """, (card_name, player, year, set_name, "Raw", image_url, embedding, datetime.now()))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id, image_url
    except Exception as e:
        st.error(f"Error saving new card: {e}")
        return None, None

# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")
st.caption("Powered by CLIP AI • Click image to +1 quantity")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Your Scanned Card", width=380)

    if st.button("🔍 Process with AI", type="primary", use_container_width=True):
        with st.spinner("AI is analyzing the card..."):
            pil_image = Image.open(uploaded_file).convert('RGB')
            embedding = get_embedding(pil_image)

            conn = get_db_connection()
            cur = conn.cursor()
            
            cur.execute("""
                SELECT id, card_name, image_url, 
                       embedding <=> %s::vector AS distance
                FROM sports_cards 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector 
                LIMIT 6
            """, (embedding, embedding))
            
            results = cur.fetchall()
            cur.close()
            conn.close()

            if results:
                st.write("### Click on a card image to increase its quantity (+1)")
                
                for row in results:
                    card_id = row[0]
                    card_name = row[1]
                    image_url = row[2]
                    distance = row[3]
                    similarity = round((1 - distance) * 100, 1)
                    
                    if image_url:
                        # Make image clickable
                        if st.image(image_url, caption=f"{card_name} ({similarity}%)", width=320):
                            new_qty = increment_qty(card_id)
                            if new_qty is not None:
                                st.success(f"✅ Quantity updated! New qty: **{new_qty}** for **{card_name}**")
                                st.rerun()

    # ===================== SAVE AS NEW CARD =====================
    st.subheader("🆕 Save as New Card")
    col1, col2 = st.columns(2)
    with col1:
        player_new = st.selectbox("Player Name", get_players(), key="new_player")
        year_new = st.number_input("Year", 1900, 2026, 2023, key="new_year")
    with col2:
        brand_new = st.selectbox("Set / Brand", get_brands(), key="new_set")
    
    if st.button("Save as New Card + Upload Image", type="secondary", use_container_width=True):
        with st.spinner("Saving new card..."):
            pil_image = Image.open(uploaded_file).convert('RGB')
            new_id, _ = save_as_new_card(pil_image, player_new, year_new, brand_new)
            if new_id:
                st.success(f"✅ New card saved! ID: {new_id} (Qty = 1)")
                st.balloons()

# Sidebar
with st.sidebar:
    st.header("Database Info")
    if st.button("View All Cards with Quantity"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, card_name, qty_available FROM sports_cards ORDER BY qty_available DESC LIMIT 15")
        for row in cur.fetchall():
            st.write(f"#{row[0]} — {row[1]} → **{row[2]}** pcs")
        cur.close()
        conn.close()

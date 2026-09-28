import streamlit as st
from PIL import Image
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from io import BytesIO

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

# Temporary debug – remove after fixing
st.write("Cloud name loaded:", bool(os.getenv("CLOUDINARY_CLOUD_NAME")))
st.write("API Key loaded:", bool(os.getenv("CLOUDINARY_API_KEY")))
st.write("API Secret loaded:", bool(os.getenv("CLOUDINARY_API_SECRET")))

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

def fix_orientation(image):
    """Fix upside-down phone photos"""
    img = image.copy()
    if img.width > img.height:  # If landscape
        img = img.rotate(180, expand=True)
    return img

def upload_to_cloudinary(pil_image):
    try:
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)
        buffer.name = "card.jpg"

        result = cloudinary.uploader.unsigned_upload(
            buffer,
            upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),
            folder="sports_cards",
            public_id=f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            resource_type="image"
        )
        return result.get("secure_url")
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def save_as_new_card(pil_image, player_name, year, brand, card_number, brand_detail, qty_available):
    try:
        image_url = upload_to_cloudinary(pil_image)
        if not image_url:
            return None

        card_name = f"{year} {brand} {player_name} #{card_number}"
        if brand_detail:
            card_name += f" ({brand_detail})"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player, year, set_name, card_number, brand_detail, image_url, qty_available, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            card_name,
            player_name,
            year,
            brand,                   

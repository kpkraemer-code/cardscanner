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

def save_as_new_card(pil_image, player_name, year, brand, card_number, brand_detail):
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
            (card_name, player, year, set_name, card_number, brand_detail, image_path, qty_available, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 1, %s)
            RETURNING id;
        """, (
            card_name,
            player_name,
            year,
            brand,
            card_number,
            brand_detail or None,
            image_url,
            datetime.utcnow()
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id, card_name, image_url
    except Exception as e:
        st.error(f"Error saving card: {e}")
        return None, None, None

# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")
st.caption("Take a photo of your card and enter the details")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    # Fix orientation and show image
    uploaded_img = Image.open(uploaded_file).convert('RGB')
    fixed_img = fix_orientation(uploaded_img)
    st.image(fixed_img, caption="Your Scanned Card", width=320)

    st.subheader("Enter Card Details")

    player_name = st.text_input("Player Name", placeholder="e.g. Michael Jordan")
    year = st.text_input("Year", placeholder="e.g. 1986")
    brand = st.text_input("Brand", placeholder="e.g. Fleer")
    card_number = st.text_input("Card Number", placeholder="e.g. 57")
    brand_detail = st.text_input("Brand Detail (optional)", placeholder="e.g. Rookie, Refractor, Parallel...")

    if st.button("💾 Save Card", type="primary", use_container_width=True):
        if not player_name or not year or not brand or not card_number:
            st.warning("Please fill in Player Name, Year, Brand, and Card Number.")
        else:
            with st.spinner("Saving card..."):
                result = save_as_new_card(
                    fixed_img, player_name, year, brand, card_number, brand_detail
                )
                if result:
                    new_id, card_name, image_url = result
                    st.success(f"✅ Saved: **{card_name}** (ID: {new_id})")
                    if image_url:
                        st.markdown(f"[View uploaded image]({image_url})")
                    st.balloons()

# Sidebar
with st.sidebar:
    st.header("Quick Stats")
    if st.button("Show Inventory"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sports_cards")
        total = cur.fetchone()[0]
        st.write(f"Total Cards: **{total}**")
        cur.close()
        conn.close()

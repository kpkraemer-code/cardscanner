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

def display_portrait_image(image, caption="Your Card"):
    """Display uploaded image in a nice portrait style"""
    st.markdown(f"""
        <div style="text-align: center; margin: 15px 0;">
            <p style="margin-bottom: 8px; font-size: 15px;">{caption}</p>
        </div>
    """, unsafe_allow_html=True)
    st.image(image, width=300)

def save_card(pil_image, player_name, year, brand, card_number, brand_detail):
    """Upload image to Cloudinary and save card details to database"""
    try:
        # Prepare image buffer (important: give it a name)
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)
        buffer.name = "card.jpg"          # ← this line often prevents upload problems

        # Upload
        upload_result = cloudinary.uploader.upload(
            buffer,
            folder="sports_cards",
            resource_type="image"
        )
        image_url = upload_result.get("secure_url")

        # Build display name
        card_name = f"{year} {brand} {player_name} #{card_number}"
        if brand_detail:
            card_name += f" ({brand_detail})"

        # Save to database
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player_name, year, brand, card_number, brand_detail, image_url, qty_available, created_at)
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
        # Print the full error so we can see exactly what Cloudinary says
        st.error(f"Error saving card: {str(e)}")
        print("Full Cloudinary / DB error:", e)   # also shows in terminal
        return None, None, None
        
# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")
st.caption("Take a photo of your card and enter the details")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    pil_image = Image.open(uploaded_file).convert('RGB')
    display_portrait_image(pil_image, "Your Scanned Card")

    st.subheader("Enter Card Details")

    player_name = st.text_input("Player Name", placeholder="e.g. Michael Jordan")
    year = st.text_input("Year", placeholder="e.g. 1986")
    brand = st.text_input("Brand", placeholder="e.g. Fleer")
    card_number = st.text_input("Card Number", placeholder="e.g. 57")
    brand_detail = st.text_input("Brand Detail (optional)", placeholder="e.g. Rookie, Refractor, Parallel, etc.")

    if st.button("💾 Save Card", type="primary", use_container_width=True):
        if not player_name or not year or not brand or not card_number:
            st.warning("Please fill in Player Name, Year, Brand, and Card Number.")
        else:
            with st.spinner("Saving card..."):
                new_id, card_name, image_url = save_card(
                    pil_image, player_name, year, brand, card_number, brand_detail
                )
                if new_id:
                    st.success(f"✅ Saved: **{card_name}** (ID: {new_id})")
                    if image_url:
                        st.markdown(f"[View uploaded image]({image_url})")

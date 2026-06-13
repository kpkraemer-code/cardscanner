import streamlit as st
from PIL import Image
import imagehash
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from io import BytesIO

st.set_page_config(page_title="Sports Card Scanner", layout="centered")

# ------------------ CLOUDINARY CONFIG ------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# ------------------ DB CONNECTION ------------------
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

# ------------------ LOAD DROPDOWN DATA ------------------
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_players():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT player_name FROM cards_players ORDER BY player_name")
        players = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return players if players else ["Unknown"]
    except:
        return ["Unknown"]

@st.cache_data(ttl=300)
def get_brands():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT brand FROM cards_brands ORDER BY brand")
        brands = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return brands if brands else ["Unknown"]
    except:
        return ["Unknown"]

# ------------------ HELPERS ------------------
def compute_phash(image):
    return str(imagehash.phash(image))

def upload_to_cloudinary(pil_image, public_id=None):
    try:
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)

        upload_result = cloudinary.uploader.unsigned_upload(
            buffer,
            upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),
            folder="sports_cards",
            public_id=public_id,
            resource_type="image"
        )
        return upload_result.get("secure_url")
    except Exception as e:
        st.error(f"Cloudinary upload failed: {str(e)}")
        return None

def find_best_match(uploaded_file):
    uploaded_image = Image.open(uploaded_file).convert('RGB')
    uploaded_hash = imagehash.phash(uploaded_image)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, card_name, phash FROM sports_cards WHERE phash IS NOT NULL")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    best_match = None
    best_diff = 999

    for row in rows:
        try:
            db_hash = imagehash.hex_to_hash(row[2])
            diff = uploaded_hash - db_hash
            if diff < best_diff:
                best_diff = diff
                best_match = {
                    'id': row[0],
                    'name': row[1],
                    'diff': diff,
                    'score': round((1 - diff / 64.0) * 100, 1)
                }
        except:
            continue

    return best_match, uploaded_image, best_diff

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner")
st.markdown("Take a photo or upload an image")

uploaded_file = st.file_uploader("Scan your sports card", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    # Display image in Portrait orientation with fixed width
    st.image(uploaded_file, caption="Scanned Card", width=380)   # Fixed width for portrait feel
    
    with st.spinner("Searching for matches..."):
        match, pil_image, best_diff = find_best_match(uploaded_file)

    # ===================== STRONG MATCH SECTION =====================
    if match and best_diff <= 18:
        st.success(f"✅ **Strong Match Found!** {match['name']} ({match['score']}%)")
        
        col1, col2 = st.columns(2)
        with col1:
            player = st.selectbox("Player Name", options=get_players(), key="player")
            year = st.number_input("Year", min_value=1900, max_value=2026, value=2023, key="year")
        with col2:
            set_name = st.selectbox("Set / Brand", options=get_brands(), key="set_name")
        
        grade = st.text_input("Grade (e.g. PSA 10)", key="grade")
        notes = st.text_area("Notes", key="notes")
        
        if st.button("💾 Add to My Collection", type="primary", use_container_width=True):
            with st.spinner("Adding to collection..."):
                # You can extend add_to_my_collection to accept image_url if needed
                new_id = add_to_my_collection(...)   # Keep your existing function
                if new_id:
                    st.success(f"✅ Added to My Collection! ID: {new_id}")
                    st.balloons()

    # ===================== SAVE AS NEW CARD =====================
    st.subheader("🆕 Save as New Card in Database")
    
    col1, col2 = st.columns(2)
    with col1:
        player_new = st.selectbox("Player Name", options=get_players(), key="new_player")
        year_new = st.number_input("Year", min_value=1900, max_value=2026, value=2023, key="new_year")
    with col2:
        brand_new = st.selectbox("Set / Brand", options=get_brands(), key="new_set_name")
    
    if st.button("Save as New Card + Upload Image", type="secondary", use_container_width=True):
        card_name = f"{player_new} - {brand_new} ({year_new})"  # Auto generate card name
        
        with st.spinner("Uploading image and saving..."):
            new_id, image_url = save_as_new_card(
                pil_image=pil_image,
                card_name=card_name,
                player=player_new,
                year=year_new,
                set_name=brand_new,
                condition="Raw"   # Removed condition dropdown
            )
            if new_id:
                st.success(f"✅ New card saved! ID: {new_id}")
                st.balloons()

# ------------------ SIDEBAR ------------------
with st.sidebar:
    st.header("My Collection")
    if st.button("View Recent Cards"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, card_name FROM my_cards ORDER BY added_at DESC LIMIT 10")
        for row in cur.fetchall():
            st.write(f"#{row[0]} — {row[1]}")
        cur.close()
        conn.close()

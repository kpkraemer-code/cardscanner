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
@st.cache_data(ttl=300)
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
        cur.execute("SELECT brand_name FROM cards_brands ORDER BY brand_name")
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

# ===================== UPDATED FUNCTIONS =====================
def add_to_my_collection(match, player, year, set_name, grade, notes):
    """Add strong match to my_cards table"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        card_name = f"{player} - {set_name} ({year})"
        
        cur.execute("""
            INSERT INTO my_cards 
            (reference_id, card_name, player, year, set_name, grade, notes, 
             scanned_at, added_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            match['id'],
            card_name,
            player,
            year,
            set_name,
            grade,
            notes,
            datetime.now(),
            datetime.now()
        ))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        st.error(f"Failed to add to collection: {e}")
        return None

def save_as_new_card(pil_image, player, year, set_name):
    """Save as new card in sports_cards table"""
    try:
        card_name = f"{player} - {set_name} ({year})"
        image_url = upload_to_cloudinary(pil_image, 
                    public_id=f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        phash_value = compute_phash(pil_image)
        
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player, year, set_name, condition, image_url, phash, scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            card_name,
            player,
            year,
            set_name,
            "Raw",                    # Default condition since dropdown was removed
            image_url,
            phash_value,
            datetime.now()
        ))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id, image_url
    except Exception as e:
        st.error(f"Error saving new card: {e}")
        return None, None

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner")
st.markdown("Take a photo or upload an image")

uploaded_file = st.file_uploader("Scan your sports card", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Scanned Card", width=380)
    
    with st.spinner("Searching for matches..."):
        match, pil_image, best_diff = find_best_match(uploaded_file)

    # ===================== STRONG MATCH =====================
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
                new_id = add_to_my_collection(
                    match=match,
                    player=player,
                    year=year,
                    set_name=set_name,
                    grade=grade,
                    notes=notes
                )
                if new_id:
                    st.success(f"✅ Added to My Collection! ID: {new_id}")
                    st.balloons()

    # ===================== SAVE

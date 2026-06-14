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
            dbname=result.path[1:], user=result.username, password=result.password,
            host=result.hostname, port=result.port, sslmode="require"
        )
    st.error("DATABASE_URL not found")
    st.stop()

# ------------------ HELPERS ------------------
def compute_phash(image):
    return str(imagehash.phash(image))

def upload_to_cloudinary(pil_image, public_id=None):
    try:
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)
        upload_result = cloudinary.uploader.unsigned_upload(
            buffer, upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),
            folder="sports_cards", public_id=public_id, resource_type="image"
        )
        return upload_result.get("secure_url")
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

def find_best_match(uploaded_file):
    uploaded_image = Image.open(uploaded_file).convert('RGB')
    uploaded_hash = imagehash.phash(uploaded_image)
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, card_name, phash, image_url 
        FROM sports_cards 
        WHERE phash IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    matches = []
    for row in rows:
        try:
            db_hash = imagehash.hex_to_hash(row[2])
            diff = uploaded_hash - db_hash
            score = round((1 - diff / 64.0) * 100, 1)
            matches.append({
                'id': row[0],
                'name': row[1],
                'diff': diff,
                'score': score,
                'image_url': row[3]
            })
        except:
            continue

    # Sort by best score
    matches.sort(key=lambda x: x['diff'])
    return matches, uploaded_image

# ------------------ SAVE FUNCTIONS (unchanged) ------------------
def add_to_my_collection(match, player, year, set_name, grade, notes):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        card_name = f"{player} - {set_name} ({year})"
        
        cur.execute("""
            INSERT INTO my_cards (reference_id, card_name, player, year, set_name, grade, notes, scanned_at, added_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (match['id'], card_name, player, year, set_name, grade, notes, datetime.now(), datetime.now()))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        st.error(f"Error: {e}")
        return None

def save_as_new_card(pil_image, player, year, set_name):
    try:
        card_name = f"{player} - {set_name} ({year})"
        image_url = upload_to_cloudinary(pil_image, public_id=f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        conn = get_db_connection()
        cur = conn.cursor()
        phash_value = compute_phash(pil_image)
        
        cur.execute("""
            INSERT INTO sports_cards (card_name, player, year, set_name, condition, image_url, phash, scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id;
        """, (card_name, player, year, set_name, "Raw", image_url, phash_value, datetime.now()))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id, image_url
    except Exception as e:
        st.error(f"Error saving card: {e}")
        return None, None

# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if 'processed' not in st.session_state:
    st.session_state.processed = False
if 'matches' not in st.session_state:
    st.session_state.matches = []

if uploaded_file:
    st.image(uploaded_file, caption="Your Scanned Card", width=380)

    if st.button("🔍 Process Image", type="primary", use_container_width=True):
        with st.spinner("Comparing to database..."):
            matches, pil_image = find_best_match(uploaded_file)
            st.session_state.matches = matches
            st.session_state.pil_image = pil_image
            st.session_state.processed = True

    if st.session_state.processed and st.session_state.matches:
        matches = st.session_state.matches
        top = matches[0]

        st.info(f"Top match score: **{top['score']}%** (Lower difference = better)")

        # Strong Match
        if top['diff'] <= 10:          # Much stricter threshold
            st.success(f"✅ **Strong Match** — {top['name']} ({top['score']}%)")
            
            col1, col2 = st.columns(2)
            with col1:
                st.image(uploaded_file, caption="Your Scan", width=300)
            with col2:
                if top.get('image_url'):
                    st.image(top['image_url'], caption="Stored Card", width=300)
            
            # Add to collection form
            col1, col2 = st.columns(2)
            with col1:
                player = st.selectbox("Player Name", get_players(), key="match_player")
                year = st.number_input("Year", 1900, 2026, 2023, key="match_year")
            with col2:
                set_name = st.selectbox("Set / Brand", get_brands(), key="match_set")
            
            grade = st.text_input("Grade", key="match_grade")
            notes = st.text_area("Notes", key="match_notes")
            
            if st.button("💾 Add to My Collection", type="primary", use_container_width=True):
                new_id = add_to_my_collection(top, player, year, set_name, grade, notes)
                if new_id:
                    st.success(f"Added! ID: {new_id}")
                    st.balloons()

        else:
            st.warning(f"**No Strong Match** — Best match is only {top['score']}% similar")
            
            st.write("### Top 3 Closest Cards:")
            for m in matches[:3]:
                st.write(f"- **{m['name']}** — {m['score']}% similar (diff: {m['diff']})")
                if m.get('image_url'):
                    st.image(m['image_url'], width=250)

        # Save as New Card (always available)
        st.subheader("🆕 Save as New Card")
        col1, col2 = st.columns(2)
        with col1:
            player_new = st.selectbox("Player Name", get_players(), key="new_player")
            year_new = st.number_input("Year", 1900, 2026, 2023, key="new_year")
        with col2:
            brand_new = st.selectbox("Set / Brand", get_brands(), key="new_set")
        
        if st.button("Save as New Card + Upload Image", type="secondary", use_container_width=True):
            with st.spinner("Saving..."):
                new_id, _ = save_as_new_card(st.session_state.pil_image, player_new, year_new, brand_new)
                if new_id:
                    st.success(f"New card saved! ID: {new_id}")
                    st.balloons()

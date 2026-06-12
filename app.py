import streamlit as st
from PIL import Image
import imagehash
import psycopg2
import os
from datetime import datetime
import io
import numpy as np
from urllib.parse import urlparse

# ------------------ CONFIG ------------------
st.set_page_config(page_title="Sports Card Scanner", layout="centered")

DB_CONFIG = {
    'dbname': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT', '5432')
}

# ------------------ HELPERS ------------------
def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        st.error("DATABASE_URL environment variable is missing!")
        st.stop()
    
    # Parse and connect
    result = urlparse(database_url)
    conn = psycopg2.connect(
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port,
        sslmode="require"
    )
    return conn

def compute_phash(image):
    return str(imagehash.phash(image))

def find_best_match(uploaded_file):
    """Compare uploaded image to database using pHash"""
    uploaded_image = Image.open(uploaded_file).convert('RGB')
    uploaded_hash = imagehash.phash(uploaded_image)
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, card_name, image_path, phash FROM sports_cards")
    rows = cur.fetchall()
    
    best_match = None
    best_score = float('inf')
    
    for row in rows:
        try:
            db_hash = imagehash.hex_to_hash(row[3])
            diff = uploaded_hash - db_hash
            if diff < best_score and diff <= 12:  # Adjust threshold
                best_score = diff
                best_match = {
                    'id': row[0],
                    'name': row[1],
                    'score': round((1 - diff / 64.0) * 100, 1)
                }
        except:
            continue
    
    cur.close()
    conn.close()
    return best_match, uploaded_image

def save_to_database(match, uploaded_image, original_filename):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Save image to a public folder or use external storage (e.g. Railway volume / Supabase)
        image_bytes = io.BytesIO()
        uploaded_image.save(image_bytes, format='JPEG')
        image_bytes = image_bytes.getvalue()
        
        # For simplicity, store as base64 or save to filesystem + path
        # Recommendation: Use a cloud bucket later
        
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player, year, set_name, condition, image_path, scanned_at, reference_id, phash)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            match.get('name', 'Unknown Card'),
            st.session_state.get('player', 'Unknown'),
            st.session_state.get('year', None),
            st.session_state.get('set_name', 'Unknown'),
            st.session_state.get('condition', 'Raw'),
            original_filename,
            datetime.now(),
            match.get('id'),
            compute_phash(uploaded_image)
        ))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        st.error(f"Database error: {e}")
        return None

# ------------------ UI ------------------
st.title("🏟️ Sports Card Scanner")
st.markdown("Take a photo or upload an image of your card")

uploaded_file = st.file_uploader(
    "Scan your sports card", 
    type=['jpg', 'jpeg', 'png'],
    help="On iPhone, tap the camera icon to take a new photo"
)

if uploaded_file:
    col1, col2 = st.columns(2)
    
    with col1:
        st.image(uploaded_file, caption="Captured Image", use_column_width=True)
    
    with col2:
        st.subheader("Processing...")
        with st.spinner("Comparing to database..."):
            match, pil_image = find_best_match(uploaded_file)
        
        if match and match['score'] > 75:
            st.success(f"**Match Found!** {match['name']}")
            st.metric("Confidence", f"{match['score']}%")
        else:
            st.warning("No strong match found. You can still save it as new.")
            match = {'name': 'New Card'}
        
        # Manual fields
        st.text_input("Player Name", key="player")
        st.number_input("Year", min_value=1900, max_value=2026, value=2023, key="year")
        st.text_input("Set / Brand", value="Unknown", key="set_name")
        st.selectbox("Condition", ["Raw", "Near Mint", "Mint", "Graded"], key="condition")
        
        if st.button("💾 Save to Collection", type="primary"):
            new_id = save_to_database(match, pil_image, uploaded_file.name)
            if new_id:
                st.success(f"Card saved successfully! Record ID: {new_id}")
                st.balloons()

# Sidebar info
with st.sidebar:
    st.header("Database")
    st.info(f"Connected to Railway Postgres")
    if st.button("View All Cards"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, card_name, scanned_at FROM sports_cards ORDER BY scanned_at DESC LIMIT 20")
        for row in cur.fetchall():
            st.write(f"#{row[0]} — {row[1]}")
        cur.close()
        conn.close()

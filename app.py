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

# ------------------ HELPERS ------------------
def compute_phash(image):
    return str(imagehash.phash(image))

def upload_to_cloudinary(pil_image, public_id=None):
    """Upload image using unsigned upload"""
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

def add_to_my_collection(match, condition, grade, notes, image_url):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO my_cards 
            (reference_id, card_name, player, year, set_name, condition, grade, notes, 
             image_url, scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            match['id'],
            match['name'],
            st.session_state.get('player'),
            st.session_state.get('year'),
            st.session_state.get('set_name'),
            condition,
            grade,
           

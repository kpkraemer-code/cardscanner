import streamlit as st
from PIL import Image
import imagehash
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse

st.set_page_config(page_title="Sports Card Scanner", layout="centered")

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
    else:
        st.error("DATABASE_URL not found")
        st.stop()

# ------------------ HELPERS ------------------
def compute_phash(image):
    return str(imagehash.phash(image))

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

def add_to_my_collection(match, uploaded_image, condition="Raw", grade=None, notes=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("""
            INSERT INTO my_cards 
            (reference_id, card_name, player, year, set_name, condition, grade, notes, scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            match['id'],
            match['name'],
            st.session_state.get('player', None),
            st.session_state.get('year', None),
            st.session_state.get('set_name', None),
            condition,
            grade,
            notes,
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

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner")
st.markdown("Take a photo or upload an image")

uploaded_file = st.file_uploader("Scan your sports card", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Scanned Card", use_column_width=True)
    
    with st.spinner("Comparing to database..."):
        match, pil_image, best_diff = find_best_match(uploaded_file)
    
    if match and best_diff <= 18:   # Strong match
        st.success(f"✅ **Strong Match Found!** {match['name']} ({match['score']}%)")
        
        # Manual fields
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Player", key="player")
            st.number_input("Year", min_value=1900, max_value=2026, value=2023, key="year")
        with col2:
            st.text_input("Set / Brand", key="set_name")
            st.selectbox("Condition", ["Raw", "Near Mint", "Mint", "Graded"], key="condition")
        
        grade = st.text_input("Grade (e.g. PSA 10)", key="grade")
        notes = st.text_area("Notes / Comments", key="notes")
        
        if st.button("💾 Add to My Collection", type="primary", use_container_width=True):
            new_id = add_to_my_collection(
                match=match,
                uploaded_image=pil_image,
                condition=st.session_state.condition,
                grade=grade,
                notes=notes
            )
            if new_id:
                st.success(f"✅ Card successfully added to **My Collection**! (ID: {new_id})")
                st.balloons()
    
    else:
        st.warning("No strong match found. You can still add it manually as a new card.")
        # You can extend this section later for manual entry without match

# ------------------ SIDEBAR ------------------
with st.sidebar:
    st.header("My Collection")
    if st.button("View My Cards"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, card_name, condition, added_at FROM my_cards ORDER BY added_at DESC LIMIT 15")
        for row in cur.fetchall():
            st.write(f"#{row[0]} — {row[1]} ({row[2]})")
        cur.close()
        conn.close()

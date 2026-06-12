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

def save_as_new_card(pil_image, card_name, player, year, set_name, condition):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        phash_value = compute_phash(pil_image)
        
        cur.execute("""
            INSERT INTO sports_cards 
            (card_name, player, year, set_name, condition, image_path, phash, scanned_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            card_name,
            player,
            year,
            set_name,
            condition,
            uploaded_file.name if 'uploaded_file' in globals() else None,
            phash_value,
            datetime.now()
        ))
        
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id
    except Exception as e:
        st.error(f"Error saving new card: {e}")
        return None

def add_to_my_collection(match, condition, grade, notes):
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
            st.session_state.get('player'),
            st.session_state.get('year'),
            st.session_state.get('set_name'),
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
        st.error(f"Error adding to collection: {e}")
        return None

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner")
st.markdown("Take a photo or upload an image of your card")

uploaded_file = st.file_uploader("Scan your sports card", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Scanned Card", use_column_width=True)
    
    with st.spinner("Comparing to database..."):
        match, pil_image, best_diff = find_best_match(uploaded_file)
    
    # ==================== STRONG MATCH ====================
    if match and best_diff <= 18:
        st.success(f"✅ **Strong Match Found!** {match['name']} ({match['score']}%)")
        
        if st.button("💾 Add to My Collection", type="primary", use_container_width=True):
            new_id = add_to_my_collection(
                match=match,
                condition=st.session_state.get('condition', 'Raw'),
                grade=st.session_state.get('grade', None),
                notes=st.session_state.get('notes', None)
            )
            if new_id:
                st.success(f"Added to My Collection! ID: {new_id}")
                st.balloons()
    
    # ==================== SAVE AS NEW CARD (Always Available) ====================
    st.subheader("Save as New Card in Database")
    
    col1, col2 = st.columns(2)
    with col1:
        card_name = st.text_input("Card Name *", value=match['name'] if match else "Unknown Card", key="new_card_name")
        player = st.text_input("Player Name", key="new_player")
        year = st.number_input("Year", min_value=1900, max_value=2026, value=2023, key="new_year")
    
    with col2:
        set_name = st.text_input("Set / Brand", key="new_set_name")
        condition = st.selectbox("Condition", ["Raw", "Near Mint", "Mint", "Graded"], key="new_condition")
    
    if st.button("🆕 Save as New Card in Database", type="secondary", use_container_width=True):
        if card_name.strip():
            new_id = save_as_new_card(
                pil_image=pil_image,
                card_name=card_name,
                player=player,
                year=year,
                set_name=set_name,
                condition=condition
            )
            if new_id:
                st.success(f"✅ New card saved successfully in sports_cards! (ID: {new_id})")
                st.balloons()
        else:
            st.error("Card Name is required")

# ------------------ SIDEBAR ------------------
with st.sidebar:
    st.header("Quick Links")
    if st.button("View My Collection"):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, card_name, condition FROM my_cards ORDER BY added_at DESC LIMIT 10")
        for row in cur.fetchall():
            st.write(f"#{row[0]} — {row[1]}")
        cur.close()
        conn.close()

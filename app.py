import streamlit as st
from PIL import Image
import imagehash
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader

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
    """Upload image using UNSIGNED upload (no signature needed)"""
    try:
        from io import BytesIO
        
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)

        upload_result = cloudinary.uploader.unsigned_upload(
            buffer,
            upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),   # <-- Important
            folder="sports_cards",
            public_id=public_id,
            overwrite=True,
            resource_type="image"
        )
        
        return upload_result.get("secure_url")
    except Exception as e:
        st.error(f"Cloudinary upload failed: {str(e)}")
        return None

def find_best_match(uploaded_file):
    # ... (keep your existing find_best_match function unchanged)
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
        image_url = upload_to_cloudinary(pil_image, public_id=f"card_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
        
        if not image_url:
            st.warning("Image upload failed, saving without image.")

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
            condition,
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

uploaded_file = st.file_uploader("Scan your sports card", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Scanned Card", use_column_width=True)
    
    with st.spinner("Comparing to database..."):
        match, pil_image, best_diff = find_best_match(uploaded_file)
    
    if match and best_diff <= 18:
        st.success(f"✅ Strong Match: {match['name']} ({match['score']}%)")
        # Add to My Collection button (keep your existing code)
    
    # === SAVE AS NEW CARD ===
    st.subheader("🆕 Save as New Card")
    
    col1, col2 = st.columns(2)
    with col1:
        card_name = st.text_input("Card Name *", value=match['name'] if match else "", key="new_card_name")
        player = st.text_input("Player", key="new_player")
        year = st.number_input("Year", 1900, 2026, 2023, key="new_year")
    with col2:
        set_name = st.text_input("Set / Brand", key="new_set_name")
        condition = st.selectbox("Condition", ["Raw", "Near Mint", "Mint", "Graded"], key="new_condition")
    
    if st.button("Save as New Card + Upload Image", type="primary", use_container_width=True):
        if card_name.strip():
            with st.spinner("Uploading image and saving card..."):
                new_id, image_url = save_as_new_card(
                    pil_image=pil_image,
                    card_name=card_name,
                    player=player,
                    year=year,
                    set_name=set_name,
                    condition=condition
                )
                if new_id:
                    st.success(f"✅ Card saved successfully! ID: {new_id}")
                    if image_url:
                        st.image(image_url, caption="Uploaded Image")
                    st.balloons()
        else:
            st.error("Card Name is required")

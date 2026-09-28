import streamlit as st
from PIL import Image
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from io import BytesIO
import requests

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
    if img.width > img.height:
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

def save_as_new_card(pil_image, player_name, year, brand, card_number, brand_detail, qty_available):
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
            (card_name, player, year, set_name, card_number, brand_detail, image_url, qty_available, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """, (
            card_name,
            player_name,
            year,
            brand,
            card_number,
            brand_detail or None,
            image_url,
            qty_available,
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

def update_card(card_id, player, year, set_name, card_number, brand_detail, qty_available):
    """Update an existing card record"""
    try:
        # Rebuild card_name for consistency
        card_name = f"{year} {set_name} {player} #{card_number}"
        if brand_detail:
            card_name += f" ({brand_detail})"

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE sports_cards
            SET card_name = %s,
                player = %s,
                year = %s,
                set_name = %s,
                card_number = %s,
                brand_detail = %s,
                qty_available = %s
            WHERE id = %s
        """, (
            card_name,
            player,
            year,
            set_name,
            card_number,
            brand_detail or None,
            qty_available,
            card_id
        ))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error updating card: {e}")
        return False

@st.cache_data(ttl=60)
def get_distinct_years():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT year FROM sports_cards WHERE year IS NOT NULL ORDER BY year DESC")
        years = [str(row[0]) for row in cur.fetchall()]
        cur.close()
        conn.close()
        return years
    except:
        return []

@st.cache_data(ttl=60)
def get_distinct_sets(year=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        if year and year != "All Years":
            cur.execute(
                "SELECT DISTINCT set_name FROM sports_cards WHERE year = %s AND set_name IS NOT NULL ORDER BY set_name",
                (year,)
            )
        else:
            cur.execute("SELECT DISTINCT set_name FROM sports_cards WHERE set_name IS NOT NULL ORDER BY set_name")
        sets = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return sets
    except:
        return []

def get_cards(year=None, set_name=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT id, card_name, player, year, set_name, card_number,
                   brand_detail, image_url, qty_available, created_at
            FROM sports_cards
            WHERE 1=1
        """
        params = []

        if year and year != "All Years":
            query += " AND year = %s"
            params.append(year)
        if set_name and set_name != "All Sets":
            query += " AND set_name = %s"
            params.append(set_name)

        query += " ORDER BY player, card_number"

        cur.execute(query, params)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"Error loading cards: {e}")
        return []

# ===================== MAIN UI =====================
st.title("🏟️ Sports Card Scanner")

tab1, tab2 = st.tabs(["📷 Add Card", "📚 Browse Cards"])

# -------------------- TAB 1: ADD CARD --------------------
with tab1:
    st.caption("Take a photo of your card and enter the details")

    uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'], key="uploader")

    if uploaded_file:
        uploaded_img = Image.open(uploaded_file).convert('RGB')
        fixed_img = fix_orientation(uploaded_img)
        st.image(fixed_img, caption="Your Scanned Card", width=320)

        st.subheader("Enter Card Details")

        player_name = st.text_input("Player Name", placeholder="e.g. Michael Jordan")
        year = st.text_input("Year", placeholder="e.g. 1986")
        brand = st.text_input("Brand / Set Name", placeholder="e.g. Fleer")
        card_number = st.text_input("Card Number", placeholder="e.g. 57")
        brand_detail = st.text_input("Brand Detail (optional)", placeholder="e.g. Rookie, Refractor, Parallel...")
        qty_available = st.number_input("Qty Available", min_value=1, value=1, step=1)

        if st.button("💾 Save Card", type="primary", use_container_width=True):
            if not player_name or not year or not brand or not card_number:
                st.warning("Please fill in Player Name, Year, Brand, and Card Number.")
            else:
                with st.spinner("Saving card..."):
                    result = save_as_new_card(
                        fixed_img, player_name, year, brand, card_number, brand_detail, qty_available
                    )
                    if result:
                        new_id, card_name, image_url = result
                        st.success(f"✅ Saved: **{card_name}** (ID: {new_id})")
                        if image_url:
                            st.markdown(f"[View uploaded image]({image_url})")
                        st.balloons()
                        st.cache_data.clear()

# -------------------- TAB 2: BROWSE CARDS --------------------
with tab2:
    st.subheader("Browse & Edit Cards")

    years = ["All Years"] + get_distinct_years()
    selected_year = st.selectbox("Select Year", years, key="browse_year")

    sets = ["All Sets"] + get_distinct_sets(selected_year)
    selected_set = st.selectbox("Select Set Name", sets, key="browse_set")

    if st.button("🔍 Load Cards", type="primary"):
        st.session_state.loaded_cards = get_cards(selected_year, selected_set)

    if "loaded_cards" in st.session_state and st.session_state.loaded_cards:
        cards = st.session_state.loaded_cards
        st.success(f"Found **{len(cards)}** card(s)")

        for card in cards:
            (card_id, card_name, player, year, set_name,
             card_number, brand_detail, image_url, qty, created_at) = card

            with st.container():
                col1, col2 = st.columns([1, 2])

                with col1:
                    if image_url:
                        try:
                            response = requests.get(image_url, stream=True, timeout=10)
                            img = Image.open(response.raw).convert("RGB")
                            # Rotate 90 degrees counter-clockwise (to the left)
                            rotated = img.rotate(90, expand=True)
                            st.image(rotated, width=220)
                        except Exception:
                            st.image(image_url, width=220)
                    else:
                        st.write("No image")

                with col2:
                    st.markdown(f"#### Card ID: {card_id}")

                    new_player = st.text_input("Player", value=player or "", key=f"player_{card_id}")
                    new_year = st.text_input("Year", value=str(year) if year else "", key=f"year_{card_id}")
                    new_set = st.text_input("Set", value=set_name or "", key=f"set_{card_id}")
                    new_number = st.text_input("Card #", value=str(card_number) if card_number else "", key=f"num_{card_id}")
                    new_detail = st.text_input("Detail", value=brand_detail or "", key=f"detail_{card_id}")
                    new_qty = st.number_input("Qty Available", min_value=0, value=int(qty or 1), step=1, key=f"qty_{card_id}")

                    if st.button("💾 Update Card", key=f"update_{card_id}", type="primary"):
                        success = update_card(
                            card_id,
                            new_player,
                            new_year,
                            new_set,
                            new_number,
                            new_detail,
                            new_qty
                        )
                        if success:
                            st.success(f"✅ Card {card_id} updated successfully!")
                            st.cache_data.clear()
                            # Refresh the loaded list
                            st.session_state.loaded_cards = get_cards(selected_year, selected_set)
                            st.rerun()

                st.divider()

    elif "loaded_cards" in st.session_state:
        st.info("No cards found for the selected filters.")

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

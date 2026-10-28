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
            (card_name, player, year, set_name, card_number, brand_detail, image_url, qty_available, created_at, orientation, price)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            datetime.utcnow(),
            0,      # default orientation
            None     # default price
        ))
        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        return new_id, card_name, image_url
    except Exception as e:
        st.error(f"Error saving card: {e}")
        return None, None, None

def update_card(card_id, player, year, set_name, card_number, brand_detail, qty_available, orientation, price, image_url=None):
    """Update an existing card record including orientation, price, and optionally the image"""
    try:
        card_name = f"{year} {set_name} {player} #{card_number}"
        if brand_detail:
            card_name += f" ({brand_detail})"

        conn = get_db_connection()
        cur = conn.cursor()

        if image_url:
            # Update including new image
            cur.execute("""
                UPDATE sports_cards
                SET card_name = %s,
                    player = %s,
                    year = %s,
                    set_name = %s,
                    card_number = %s,
                    brand_detail = %s,
                    qty_available = %s,
                    orientation = %s,
                    price = %s,
                    image_url = %s
                WHERE id = %s
            """, (
                card_name,
                player,
                year,
                set_name,
                card_number,
                brand_detail or None,
                qty_available,
                orientation,
                price,
                image_url,
                card_id
            ))
        else:
            # Update without changing image
            cur.execute("""
                UPDATE sports_cards
                SET card_name = %s,
                    player = %s,
                    year = %s,
                    set_name = %s,
                    card_number = %s,
                    brand_detail = %s,
                    qty_available = %s,
                    orientation = %s,
                    price = %s
                WHERE id = %s
            """, (
                card_name,
                player,
                year,
                set_name,
                card_number,
                brand_detail or None,
                qty_available,
                orientation,
                price,
                card_id
            ))

        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error updating card: {e}")
        return False

def delete_card(card_id):
    """Delete a single card record by ID"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM sports_cards WHERE id = %s", (card_id,))
        conn.commit()
        cur.close()
        conn.close()
        return True
    except Exception as e:
        st.error(f"Error deleting card: {e}")
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

@st.cache_data(ttl=60)
def get_distinct_players(year=None, set_name=None):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        query = "SELECT DISTINCT player FROM sports_cards WHERE player IS NOT NULL"
        params = []

        if year and year != "All Years":
            query += " AND year = %s"
            params.append(year)
        if set_name and set_name != "All Sets":
            query += " AND set_name = %s"
            params.append(set_name)

        query += " ORDER BY player"
        cur.execute(query, params)
        players = [row[0] for row in cur.fetchall()]
        cur.close()
        conn.close()
        return players
    except:
        return []

def get_cards(year=None, set_name=None, player=None, card_number=None, sort_by="player"):
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        query = """
            SELECT id, card_name, player, year, set_name, card_number,
                   brand_detail, image_url, qty_available, created_at, orientation, price
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
        if player and player != "All Players":
            query += " AND player = %s"
            params.append(player)
        if card_number and card_number.strip():
            query += " AND card_number = %s"
            params.append(card_number.strip())

        # Sorting options
        if sort_by == "qty_desc":
            query += " ORDER BY qty_available DESC NULLS LAST, player ASC, card_number ASC"
        else:
            query += " ORDER BY player ASC, card_number ASC"

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

    # Filters
    years = ["All Years"] + get_distinct_years()
    selected_year = st.selectbox("Select Year", years, key="browse_year")

    sets = ["All Sets"] + get_distinct_sets(selected_year)
    selected_set = st.selectbox("Select Set Name", sets, key="browse_set")

    players = ["All Players"] + get_distinct_players(selected_year, selected_set)
    selected_player = st.selectbox("Select Player Name", players, key="browse_player")

    card_number_filter = st.text_input(
        "Card Number",
        placeholder="e.g. 57 (leave blank for all)",
        key="browse_card_number"
    )

    # Sort option
    sort_option = st.selectbox(
        "Sort by",
        options=["Player (A-Z)", "Quantity (High → Low)"],
        key="browse_sort"
    )

    sort_by = "qty_desc" if sort_option == "Quantity (High → Low)" else "player"

    if st.button("🔍 Load Cards", type="primary"):
        st.session_state.loaded_cards = get_cards(
            selected_year,
            selected_set,
            selected_player,
            card_number_filter,
            sort_by=sort_by
        )

    if "loaded_cards" in st.session_state and st.session_state.loaded_cards:
        cards = st.session_state.loaded_cards
        st.success(f"Found **{len(cards)}** card(s)")

        for card in cards:
            (card_id, card_name, player, year, set_name,
             card_number, brand_detail, image_url, qty, created_at, orientation, price) = card

            # Defaults
            current_orientation = orientation if orientation is not None else 0
            current_price = float(price) if price is not None else 0.00

            with st.container():
                col1, col2 = st.columns([1, 2])

                with col2:
                    st.markdown(f"#### Card ID: {card_id}")

                    new_player = st.text_input("Player", value=player or "", key=f"player_{card_id}")
                    new_year = st.text_input("Year", value=str(year) if year else "", key=f"year_{card_id}")
                    new_set = st.text_input("Set", value=set_name or "", key=f"set_{card_id}")
                    new_number = st.text_input("Card #", value=str(card_number) if card_number else "", key=f"num_{card_id}")
                    new_detail = st.text_input("Detail", value=brand_detail or "", key=f"detail_{card_id}")
                    new_qty = st.number_input("Qty Available", min_value=0, value=int(qty or 1), step=1, key=f"qty_{card_id}")

                    new_price = st.number_input(
                        "Price ($)",
                        min_value=0.00,
                        value=current_price,
                        step=0.01,
                        format="%.2f",
                        key=f"price_{card_id}"
                    )

                    # Orientation selector with live preview
                    new_orientation = st.selectbox(
                        "Image Orientation",
                        options=[0, 90, 180, 270],
                        index=[0, 90, 180, 270].index(current_orientation) if current_orientation in [0, 90, 180, 270] else 1,
                        key=f"orient_{card_id}",
                        help="0 = normal, 90 = rotate left, 180 = upside down, 270 = rotate right"
                    )

                    # NEW: Image update uploader
                    new_image_file = st.file_uploader(
                        "Update Image (optional – leave empty to keep current)",
                        type=['jpg', 'jpeg', 'png'],
                        key=f"img_upload_{card_id}"
                    )

                with col1:
                    # Show current image (or newly selected one for preview)
                    display_img = None
                    if new_image_file:
                        try:
                            preview_img = Image.open(new_image_file).convert("RGB")
                            preview_img = fix_orientation(preview_img)
                            rotated = preview_img.rotate(new_orientation, expand=True)
                            st.image(rotated, width=220, caption=f"New image preview: {new_orientation}°")
                            display_img = "new"
                        except Exception:
                            st.write("Could not preview new image")
                    elif image_url:
                        try:
                            response = requests.get(image_url, stream=True, timeout=10)
                            img = Image.open(response.raw).convert("RGB")
                            rotated = img.rotate(new_orientation, expand=True)
                            st.image(rotated, width=220, caption=f"Current: {new_orientation}°")
                        except Exception:
                            st.image(image_url, width=220)
                    else:
                        st.write("No image")

                # Buttons
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("💾 Update Card", key=f"update_{card_id}", type="primary", use_container_width=True):
                        new_image_url = None

                        # If a new image was uploaded, process and upload it
                        if new_image_file:
                            with st.spinner("Uploading new image..."):
                                try:
                                    uploaded_img = Image.open(new_image_file).convert("RGB")
                                    fixed_img = fix_orientation(uploaded_img)
                                    new_image_url = upload_to_cloudinary(fixed_img)
                                    if not new_image_url:
                                        st.error("Failed to upload new image. Other fields will still be updated.")
                                except Exception as e:
                                    st.error(f"Error processing new image: {e}")

                        success = update_card(
                            card_id,
                            new_player,
                            new_year,
                            new_set,
                            new_number,
                            new_detail,
                            new_qty,
                            new_orientation,
                            new_price,
                            image_url=new_image_url   # None if no new image
                        )
                        if success:
                            msg = f"✅ Card {card_id} updated successfully!"
                            if new_image_url:
                                msg += " (image replaced)"
                            st.success(msg)
                            st.cache_data.clear()
                            st.session_state.loaded_cards = get_cards(
                                selected_year,
                                selected_set,
                                selected_player,
                                card_number_filter,
                                sort_by=sort_by
                            )
                            st.rerun()

                with btn_col2:
                    if st.button("🗑️ Delete Card", key=f"delete_{card_id}", type="secondary", use_container_width=True):
                        if delete_card(card_id):
                            st.success(f"✅ Card {card_id} deleted successfully!")
                            st.cache_data.clear()
                            st.session_state.loaded_cards = get_cards(
                                selected_year,
                                selected_set,
                                selected_player,
                                card_number_filter,
                                sort_by=sort_by
                            )
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

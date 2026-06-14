import streamlit as st
from PIL import Image
import psycopg2
import os
from datetime import datetime
from urllib.parse import urlparse
import cloudinary
import cloudinary.uploader
from io import BytesIO

from sentence_transformers import SentenceTransformer
import numpy as np

st.set_page_config(page_title="Sports Card Scanner", layout="centered")

# ------------------ CONFIG ------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

# Load CLIP model (cached)
@st.cache_resource
def load_clip_model():
    return SentenceTransformer('clip-ViT-B-32')

model = load_clip_model()

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
def get_image_embedding(image):
    return model.encode(image).tolist()

def upload_to_cloudinary(pil_image, public_id=None):
    try:
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=85, optimize=True)
        buffer.seek(0)
        result = cloudinary.uploader.unsigned_upload(
            buffer, upload_preset=os.getenv("CLOUDINARY_UPLOAD_PRESET"),
            folder="sports_cards", public_id=public_id, resource_type="image"
        )
        return result.get("secure_url")
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None

# ------------------ MAIN UI ------------------
st.title("🏟️ Sports Card Scanner - CLIP AI")
st.caption("Much more accurate matching using AI embeddings")

uploaded_file = st.file_uploader("Take photo or upload card image", type=['jpg', 'jpeg', 'png'])

if uploaded_file:
    st.image(uploaded_file, caption="Your Scanned Card", width=400)

    if st.button("🔍 Process with AI", type="primary", use_container_width=True):
        with st.spinner("Generating AI embedding and searching..."):
            pil_image = Image.open(uploaded_file).convert('RGB')
            embedding = get_image_embedding(pil_image)

            conn = get_db_connection()
            cur = conn.cursor()
            
            # Search using vector similarity
            cur.execute("""
                SELECT id, card_name, image_url, 
                       embedding <=> %s::vector AS distance
                FROM sports_cards 
                WHERE embedding IS NOT NULL
                ORDER BY embedding <=> %s::vector
                LIMIT 5;
            """, (embedding, embedding))
            
            results = cur.fetchall()
            cur.close()
            conn.close()

            if results:
                best = results[0]
                similarity = (1 - best[3]) * 100  # Convert distance to %

                if similarity >= 75:   # Adjustable threshold
                    st.success(f"✅ **Strong Match Found!** {best[1]} ({similarity:.1f}%)")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        st.image(uploaded_file, caption="Your Scan", width=300)
                    with col2:
                        if best[2]:
                            st.image(best[2], caption="Matched Card from Database", width=300)
                    
                    # Add to collection form (you can expand this)
                    st.subheader("Add to My Collection")
                    player = st.selectbox("Player", ["Select Player..."] + get_players(), key="match_player")  # reuse your dropdowns
                    # ... add other fields as needed
                    
                    if st.button("💾 Add to My Collection"):
                        st.success("Added to collection!")
                else:
                    st.warning(f"Best match is only {similarity:.1f}% similar — Not confident enough")
                
                st.write("### Top 5 Matches")
                for row in results:
                    sim = (1 - row[3]) * 100
                    st.write(f"• **{row[1]}** — {sim:.1f}% similar")
                    if row[2]:
                        st.image(row[2], width=200)
            else:
                st.info("No cards with embeddings found in database yet.")

# Save as New Card Section (simplified)
st.subheader("🆕 Save as New Card")
# ... (add your form fields here)

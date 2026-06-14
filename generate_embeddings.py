import psycopg2
from sentence_transformers import SentenceTransformer
from PIL import Image
import os
from io import BytesIO
import cloudinary
import cloudinary.api

# ------------------ CONFIG ------------------
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

model = SentenceTransformer('clip-ViT-B-32')

def get_db_connection():
    database_url = os.getenv("DATABASE_URL")
    result = urlparse(database_url)
    return psycopg2.connect(
        dbname=result.path[1:], user=result.username, password=result.password,
        host=result.hostname, port=result.port, sslmode="require"
    )

def generate_embedding_from_url(image_url):
    try:
        import requests
        response = requests.get(image_url, timeout=10)
        img = Image.open(BytesIO(response.content)).convert('RGB')
        return model.encode(img).tolist()
    except:
        return None

# ===================== BULK GENERATION =====================
conn = get_db_connection()
cur = conn.cursor()

cur.execute("SELECT id, image_url FROM sports_cards WHERE embedding IS NULL AND image_url IS NOT NULL LIMIT 50")
cards = cur.fetchall()

print(f"Found {len(cards)} cards without embeddings.")

for card_id, image_url in cards:
    if not image_url:
        continue
        
    print(f"Processing card {card_id}...")
    embedding = generate_embedding_from_url(image_url)
    
    if embedding:
        cur.execute(
            "UPDATE sports_cards SET embedding = %s::vector WHERE id = %s",
            (embedding, card_id)
        )
        conn.commit()
        print(f"✅ Updated card {card_id}")
    else:
        print(f"❌ Failed card {card_id}")

cur.close()
conn.close()
print("Bulk embedding generation completed!")

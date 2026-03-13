import edge_tts
import hashlib
import os

VOICE = "en-US-ChristopherNeural"
CACHE_DIR = "src/api/static/tts_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

async def text_to_speech(text: str) -> str:
    clean = text.replace('*','').replace('_','').replace('#','').replace('`','').strip()
    if not clean:
        return None
    hash_key = hashlib.md5(clean.encode()).hexdigest()
    cache_file = f"{CACHE_DIR}/{hash_key}.mp3"
    if os.path.exists(cache_file):
        return cache_file
    communicate = edge_tts.Communicate(clean, VOICE)
    await communicate.save(cache_file)
    return cache_file
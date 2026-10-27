import os
from pathlib import Path
from dotenv import load_dotenv

# .env faylini aynan shu papka ichidan aniq topib o'qish
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(dotenv_path=BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
TMDB_API_KEY = os.getenv("TMDB_API_KEY")

TEMP_DIR = BASE_DIR / "temp"
os.makedirs(TEMP_DIR, exist_ok=True)

# Agar token hali ham topilmasa, sababini ekranga chiqaradi
if not BOT_TOKEN:
    print("❌ XATOLIK: .env fayli ichidan BOT_TOKEN topilmadi!")
    print(f"📁 Hozirgi papka ichidagi fayllar: {os.listdir(BASE_DIR)}")
    exit()
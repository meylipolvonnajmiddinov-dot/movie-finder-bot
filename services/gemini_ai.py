import json
import time
from google import genai
from google.genai import types
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
Sen professional kinoekspertsan. Vazifang — foydalanuvchi yuborgan video parcha yoki matnli ta'rif asosida u qaysi kino, serial yoki multfilm ekanligini topish.

Javobni FAQAT quyidagi JSON formatda qaytar:
{
    "found": true,
    "title_original": "Kinoning asl nomi",
    "title_uz": "Kinoning o'zbekcha nomi",
    "year": 2023,
    "type": "Kino",
    "description_uz": "Kino haqida qisqacha ma'lumot"
}

Agar kinoni aniqlab bo'lmasa, "found": false qilib qaytar.
"""

# Siz so'ragan barcha 4 ta model (navbatma-navbat ishlaydi):
MODELS = [
    "gemini-3.8-flash",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
]


def _generate_from_any_model(contents):
    """Modellarni navbatma-navbat aylantirib, birinchi ishlaganidan javob oladi"""
    errors = []
    
    # 2 marta to'liq aylana qiladi (jami 8 ta urinish)
    for round_num in range(2):
        for model_name in MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        response_mime_type="application/json",
                        temperature=0.2,
                    ),
                )
                print(f"✅ [{model_name}] muvaffaqiyatli javob berdi!")
                return json.loads(response.text)
            except Exception as e:
                err_msg = str(e)
                print(f"⚠️ [{model_name}] ishlamadi (keyingisiga o'tilmoqda): {err_msg[:90]}")
                errors.append(f"{model_name}: {err_msg[:40]}")
                continue
        
        # Agar 4 ta modelning hammasi band bo'lsa, 2 soniya kutib qayta aylanadi
        time.sleep(2)
        
    raise Exception(" | ".join(errors[-2:]))


def analyze_text(user_text: str) -> dict:
    try:
        return _generate_from_any_model(f"Ushbu ta'rif bo'yicha kinoni top: {user_text}")
    except Exception as e:
        print(f"❌ BARCHA MODELLAR XATO BERDI (TEXT): {str(e)}")
        return {
            "found": False, 
            "description_uz": "Hozirda barcha AI serverlari band. Iltimos, 10 soniyadan so'ng qayta yuboring."
        }


def analyze_video(video_path: str) -> dict:
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            return {"found": False, "description_uz": "Videoni o'qishda xatolik yuz berdi."}

        return _generate_from_any_model([uploaded_file, "Ushbu videodagi kino yoki serialni aniqla."])

    except Exception as e:
        print(f"❌ BARCHA MODELLAR XATO BERDI (VIDEO): {str(e)}")
        return {
            "found": False, 
            "description_uz": "Videoni tahlil qilishda serverlar band bo'ldi. Birozdan so'ng qayta yuboring."
        }

    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
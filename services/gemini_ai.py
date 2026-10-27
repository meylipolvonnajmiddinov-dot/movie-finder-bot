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

# Agar bitta model band (503) bo'lsa, darhol kutmasdan keyingisiga o'tadi:
MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash",
    "gemini-1.5-flash",
]


def _generate_fast_fallback(contents):
    last_error = None
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
            return json.loads(response.text)
        except Exception as e:
            last_error = e
            print(f"⚠️ [{model_name}] xato berdi, keyingi modelga o'tilmoqda: {str(e)[:80]}")
            continue
    raise last_error


def analyze_text(user_text: str) -> dict:
    try:
        return _generate_fast_fallback(f"Ushbu ta'rif bo'yicha kinoni top: {user_text}")
    except Exception as e:
        print(f"❌ GEMINI TEXT XATOLIK: {str(e)}")
        return {"found": False, "description_uz": f"AI xatosi: {str(e)[:60]}"}


def analyze_video(video_path: str) -> dict:
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            return {"found": False, "description_uz": "Videoni o'qishda xatolik yuz berdi."}

        return _generate_fast_fallback([uploaded_file, "Ushbu videodagi kino yoki serialni aniqla."])

    except Exception as e:
        print(f"❌ GEMINI VIDEO XATOLIK: {str(e)}")
        return {"found": False, "description_uz": f"Video AI xatosi: {str(e)[:60]}"}

    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
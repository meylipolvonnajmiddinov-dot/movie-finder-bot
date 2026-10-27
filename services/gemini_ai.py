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

def analyze_text(user_text: str) -> dict:
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=f"Ushbu ta'rif bo'yicha kinoni top: {user_text}",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"❌ GEMINI TEXT XATOLIK: {str(e)}")
        return {"found": False, "description_uz": f"Xatolik tafsiloti: {str(e)[:50]}"}


def analyze_video(video_path: str) -> dict:
    uploaded_file = None
    try:
        uploaded_file = client.files.upload(file=video_path)
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(2)
            uploaded_file = client.files.get(name=uploaded_file.name)

        if uploaded_file.state.name == "FAILED":
            return {"found": False, "description_uz": "Videoni o'qishda xatolik yuz berdi."}

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=[uploaded_file, "Ushbu videodagi kino yoki serialni aniqla."],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                temperature=0.2,
            ),
        )
        return json.loads(response.text)

    except Exception as e:
        print(f"❌ GEMINI VIDEO XATOLIK: {str(e)}")
        return {"found": False, "description_uz": f"Video xatoligi: {str(e)[:50]}"}

    finally:
        if uploaded_file:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
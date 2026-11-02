import asyncio
import json
import os
import random
import logging
from google import genai
from google.genai import types, errors
from config import GEMINI_API_KEY

log = logging.getLogger(__name__)
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

# Asosiy va zaxira modellar (.env da bo'lmasa, shu ro'yxat ishlaydi)
MODELS = [
    m.strip() for m in os.getenv(
        "GEMINI_MODELS", 
        "gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite"
    ).split(",") if m.strip()
]

RETRYABLE = {429, 500, 503, 504}
REQUEST_TIMEOUT = 60          # soniya
MAX_ATTEMPTS_PER_MODEL = 3

_dead_models: set[str] = set()                 # 404 bergan modellarni eslab qolish
_semaphore = asyncio.Semaphore(3)              # bir vaqtda ko'pi bilan 3 ta so'rov


async def _generate_from_any_model(contents) -> dict:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.2,
    )
    last_error = None

    async with _semaphore:
        for model in MODELS:
            if model in _dead_models:
                continue

            for attempt in range(MAX_ATTEMPTS_PER_MODEL):
                try:
                    resp = await asyncio.wait_for(
                        client.aio.models.generate_content(
                            model=model, contents=contents, config=config
                        ),
                        timeout=REQUEST_TIMEOUT,
                    )
                    data = json.loads(resp.text)
                    # Ba'zan Gemini ro'yxat [{...}] qaytarishi mumkin, uni dict ga o'tkazamiz
                    if isinstance(data, list) and len(data) > 0:
                        data = data[0]
                    print(f"✅ [{model}] muvaffaqiyatli javob berdi!")
                    return data

                except errors.APIError as e:
                    last_error = e
                    if e.code == 404:
                        log.error("Model topilmadi (404), ro'yxatdan chiqarildi: %s", model)
                        _dead_models.add(model)
                        break  # Darhol keyingi modelga o'tish

                    if e.code in RETRYABLE:
                        delay = (2 ** attempt) + random.random()
                        log.warning("%s -> %s, %.1fs kutib qayta urinamiz...", model, e.code, delay)
                        await asyncio.sleep(delay)
                        continue  # Shu modelni qayta urinish

                    raise  # 400, 403 kabi xatolarda qayta urinmaymiz

                except asyncio.TimeoutError as e:
                    last_error = e
                    log.warning("%s timeout (urinish %d)", model, attempt + 1)
                    continue

                except json.JSONDecodeError as e:
                    last_error = e
                    break  # JSON buzilgan bo'lsa, keyingi modelni sinab ko'ramiz

    raise RuntimeError(f"Barcha modellar muvaffaqiyatsiz: {last_error!r}")


async def analyze_text(user_text: str) -> dict:
    try:
        return await _generate_from_any_model(
            f"Ushbu ta'rif bo'yicha kinoni top: {user_text}"
        )
    except Exception as e:
        log.exception("analyze_text xatosi: %s", e)
        return {
            "found": False,
            "description_uz": "Hozirda AI serverlari band. Birozdan so'ng qayta yuboring.",
        }


async def analyze_video(video_path: str) -> dict:
    uploaded = None
    try:
        uploaded = await client.aio.files.upload(file=video_path)

        # Videoning Google serverida qayta ishlanishini asinxron kutish (maksimum ~2 daqiqa)
        for _ in range(60):
            if uploaded.state.name != "PROCESSING":
                break
            await asyncio.sleep(2)
            uploaded = await client.aio.files.get(name=uploaded.name)
        else:
            return {"found": False, "description_uz": "Video juda uzoq qayta ishlandi."}

        if uploaded.state.name == "FAILED":
            return {"found": False, "description_uz": "Videoni o'qishda xatolik yuz berdi."}

        return await _generate_from_any_model(
            [uploaded, "Ushbu videodagi kino yoki serialni aniqla."]
        )
    except Exception as e:
        log.exception("analyze_video xatosi: %s", e)
        return {
            "found": False,
            "description_uz": "Videoni tahlil qilishda xatolik. Birozdan so'ng qayta yuboring.",
        }
    finally:
        if uploaded:
            try:
                await client.aio.files.delete(name=uploaded.name)
            except Exception:
                pass
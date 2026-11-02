import asyncio
import json
import logging
import random

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

# Asosiy va zaxira modellar. Navbatma-navbat sinab ko'riladi:
# birinchisi ishlamasa (band, topilmadi va h.k.), keyingisiga o'tiladi.
MODELS = [
    "gemini-3.8-flash",
    "gemini-3.7-flash",
    "gemini-2.5-flash",
]

RETRYABLE = {429, 500, 503, 504}   # vaqtinchalik xatolar: shu modelni qayta urinib ko'ramiz
REQUEST_TIMEOUT = 60               # bitta so'rov uchun maksimal kutish (soniya)
MAX_ATTEMPTS_PER_MODEL = 3

_dead_models: set[str] = set()     # 404 bergan modellarni eslab qolamiz
_semaphore = asyncio.Semaphore(3)  # bir vaqtda ko'pi bilan 3 ta so'rov


def _parse_json(text: str | None) -> dict:
    """Gemini javobini dict ga aylantiradi. Yaroqsiz bo'lsa ValueError ko'taradi."""
    if not text:
        raise ValueError("Gemini bo'sh javob qaytardi")
    data = json.loads(text)  # buzuq JSON bo'lsa JSONDecodeError (ValueError turi) chiqadi
    # Ba'zan Gemini ro'yxat [{...}] qaytaradi, birinchi elementni olamiz
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        raise ValueError(f"Kutilmagan javob turi: {type(data).__name__}")
    return data


async def _generate_from_any_model(contents) -> dict:
    # Diqqat: temperature ataylab berilmagan. Gemini 3.x modellari uchun Google
    # standart qiymatni (1.0) qoldirishni tavsiya qiladi, pastroq qiymat
    # takrorlanish yoki sifat pasayishiga olib kelishi mumkin.
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
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
                    data = _parse_json(resp.text)
                    log.info("[%s] javob berdi", model)
                    return data

                except errors.APIError as e:
                    last_error = e
                    code = e.code

                    if code == 404:
                        log.error("Model topilmadi (404), ro'yxatdan chiqarildi: %s", model)
                        _dead_models.add(model)
                        break  # darhol keyingi modelga o'tamiz

                    if code in RETRYABLE:
                        if attempt == MAX_ATTEMPTS_PER_MODEL - 1:
                            log.warning("%s -> %s, urinishlar tugadi, keyingi modelga o'tamiz", model, code)
                            break
                        delay = (2 ** attempt) + random.random()
                        log.warning("%s -> %s, %.1f soniya kutib qayta urinamiz", model, code, delay)
                        await asyncio.sleep(delay)
                        continue  # shu modelni qayta urinamiz

                    # 400, 403 va boshqa xatolar: qayta urinish befoyda, lekin
                    # butun zanjirni to'xtatmaymiz, keyingi modelni sinab ko'ramiz.
                    log.warning("%s -> %s: %s. Keyingi modelga o'tamiz", model, code, e)
                    break

                except asyncio.TimeoutError as e:
                    last_error = e
                    log.warning("%s: %d soniyada javob kelmadi, keyingi modelga o'tamiz", model, REQUEST_TIMEOUT)
                    break

                except ValueError as e:
                    # Bo'sh yoki buzuq JSON javob
                    last_error = e
                    log.warning("%s: javobni o'qib bo'lmadi (%r), keyingi modelga o'tamiz", model, e)
                    break

                except Exception as e:  # tarmoq xatolari va boshqa kutilmagan holatlar
                    last_error = e
                    log.warning("%s: kutilmagan xato %r, keyingi modelga o'tamiz", model, e)
                    break

    raise RuntimeError(
        f"Barcha modellar muvaffaqiyatsiz. Oxirgi xato: {last_error!r}; "
        f"o'chirilgan modellar: {sorted(_dead_models)}"
    )


async def analyze_text(user_text: str) -> dict:
    try:
        return await _generate_from_any_model(
            f"Ushbu ta'rif bo'yicha kinoni top: {user_text}"
        )
    except Exception:
        log.exception("analyze_text xatosi")
        return {
            "found": False,
            "description_uz": "Hozirda AI serverlari band. Birozdan so'ng qayta yuboring.",
        }


async def analyze_video(video_path: str) -> dict:
    uploaded = None
    try:
        uploaded = await client.aio.files.upload(file=video_path)

        # Video Google serverida qayta ishlanishini kutamiz (ko'pi bilan ~2 daqiqa)
        for _ in range(60):
            if uploaded.state.name != "PROCESSING":
                break
            await asyncio.sleep(2)
            uploaded = await client.aio.files.get(name=uploaded.name)

        state = uploaded.state.name
        if state == "PROCESSING":
            return {"found": False, "description_uz": "Video juda uzoq qayta ishlandi."}
        if state == "FAILED":
            return {"found": False, "description_uz": "Videoni o'qishda xatolik yuz berdi."}

        return await _generate_from_any_model(
            [uploaded, "Ushbu videodagi kino yoki serialni aniqla."]
        )
    except Exception:
        log.exception("analyze_video xatosi")
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
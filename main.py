import os
import asyncio
import logging
from urllib.parse import quote_plus
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode

from config import BOT_TOKEN, TEMP_DIR
from services.gemini_ai import analyze_text, analyze_video
from services.tmdb import get_movie_details
from services.database import init_db, add_user, save_search, get_bot_stats, get_user_history

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

def get_start_keyboard() -> InlineKeyboardMarkup:
    """Bosh sahifa tugmalari"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📜 Mening qidiruvlarim", callback_data="my_history"),
            InlineKeyboardButton(text="📊 Statistika", callback_data="bot_stats")
        ]
    ])

def get_movie_keyboard(title_orig: str, title_uz: str, year: str) -> InlineKeyboardMarkup:
    """Topilgan kino ostida chiqadigan tugmalar"""
    yt_query = quote_plus(f"{title_orig} {year} official trailer")
    uz_query = quote_plus(f"{title_uz} {year} uzbek tilida kino")
    
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="▶️ Treylerni ko'rish (YouTube)", url=f"https://www.youtube.com/results?search_query={yt_query}")
        ],
        [
            InlineKeyboardButton(text="🇺🇿 O'zbek tilida izlash (Google)", url=f"https://www.google.com/search?q={uz_query}")
        ],
        [
            InlineKeyboardButton(text="📜 Qidiruv tarixim", callback_data="my_history")
        ]
    ])

@dp.message(CommandStart())
async def cmd_start(message: Message):
    user = message.from_user
    await add_user(user.id, user.full_name, user.username)

    await message.answer(
        f"Salom, <b>{user.full_name}</b>! 🎬\n\n"
        "Men sun'iy intellekt yordamida kinolarni topuvchi botman.\n"
        "📹 Menga kinodan <b>qisqa video (Reels/Shorts)</b> yuboring yoki\n"
        "✍️ Kino syujetini <b>matn ko'rinishida</b> yozib yuboring!",
        parse_mode=ParseMode.HTML,
        reply_markup=get_start_keyboard()
    )

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    stats = await get_bot_stats()
    await message.answer(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']}</b> ta\n"
        f"🔍 Jami qidiruvlar soni: <b>{stats['searches']}</b> ta",
        parse_mode=ParseMode.HTML
    )

# INLINE TUGMALAR BOSILGANDA ISHLAYDIGAN QISM
@dp.callback_query(F.data == "bot_stats")
async def cb_stats(callback: CallbackQuery):
    stats = await get_bot_stats()
    await callback.message.answer(
        f"📊 <b>Bot statistikasi:</b>\n\n"
        f"👥 Jami foydalanuvchilar: <b>{stats['users']}</b> ta\n"
        f"🔍 Jami qidiruvlar soni: <b>{stats['searches']}</b> ta",
        parse_mode=ParseMode.HTML
    )
    await callback.answer()

@dp.callback_query(F.data == "my_history")
async def cb_history(callback: CallbackQuery):
    history = await get_user_history(callback.from_user.id)
    if not history:
        await callback.answer("Sizda hali qidiruvlar tarixi yo'q.", show_alert=True)
        return

    text = "📜 <b>Sizning oxirgi 5 ta qidiruvingiz:</b>\n\n"
    for i, (q_type, movie, ts) in enumerate(history, 1):
        icon = "📹" if q_type == "video" else "✍️"
        text += f"{i}. {icon} <b>{movie}</b> <i>({ts[:16]})</i>\n"

    await callback.message.answer(text, parse_mode=ParseMode.HTML)
    await callback.answer()

async def send_movie_result(message: Message, wait_msg: Message, result: dict, q_type: str, q_info: str):
    if not result.get("found"):
        await save_search(message.from_user.id, q_type, q_info, "Topilmadi")
        await wait_msg.edit_text(
            f"😔 <b>Kechirasiz, kinoni aniqlay olmadim.</b>\n"
            f"💡 <i>Izoh: {result.get('description_uz', 'Boshqacharoq video yoki ta\'rif yuborib ko\'ring.')}</i>",
            parse_mode=ParseMode.HTML
        )
        return

    title_orig = result.get("title_original", "Noma'lum")
    title_uz = result.get("title_uz", title_orig)
    year = result.get("year", "")
    m_type = result.get("type", "Kino")
    desc = result.get("description_uz", "")

    # Bazaga topilgan kino nomi bilan saqlaymiz
    await save_search(message.from_user.id, q_type, q_info, f"{title_uz} ({year})")

    tmdb_data = await get_movie_details(title_orig, year)
    rating = tmdb_data.get("rating", "—") if tmdb_data else "—"
    poster_url = tmdb_data.get("poster_url") if tmdb_data else None

    caption = (
        f"🎬 <b>{title_uz}</b> ({year})\n"
        f"🌐 <b>Asl nomi:</b> {title_orig}\n"
        f"📁 <b>Turi:</b> {m_type} | ⭐ <b>Reyting:</b> {rating}/10\n\n"
        f"📖 <b>Qisqacha mazmuni:</b>\n{desc}"
    )

    keyboard = get_movie_keyboard(title_orig, title_uz, str(year))
    await wait_msg.delete()

    if poster_url:
        await message.answer_photo(photo=poster_url, caption=caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)
    else:
        await message.answer(caption, parse_mode=ParseMode.HTML, reply_markup=keyboard)

@dp.message(F.video)
async def handle_video(message: Message):
    if message.video.file_size > 20 * 1024 * 1024:
        await message.answer("⚠️ Video hajmi juda katta! Iltimos, 20 MB dan kichikroq video yuboring.")
        return

    await add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    wait_msg = await message.answer("⏳ <i>Video yuklanmoqda va AI tomonidan tahlil qilinmoqda...</i>", parse_mode=ParseMode.HTML)
    video_path = os.path.join(TEMP_DIR, f"{message.video.file_unique_id}.mp4")

    try:
        await bot.download(message.video, destination=video_path)
        result = await asyncio.to_thread(analyze_video, video_path)
        await send_movie_result(message, wait_msg, result, "video", "Video parcha")
    except Exception as e:
        logging.error(f"Video handler xatosi: {e}")
        await wait_msg.edit_text("❌ Videoni qayta ishlashda xatolik yuz berdi.")
    finally:
        if os.path.exists(video_path):
            os.remove(video_path)

@dp.message(F.text)
async def handle_text(message: Message):
    await add_user(message.from_user.id, message.from_user.full_name, message.from_user.username)
    wait_msg = await message.answer("🔍 <i>Ta'rif bo'yicha kino qidirilmoqda...</i>", parse_mode=ParseMode.HTML)
    result = await asyncio.to_thread(analyze_text, message.text)
    await send_movie_result(message, wait_msg, result, "text", message.text[:100])

async def main():
    await init_db()
    logging.basicConfig(level=logging.INFO)
    print("🚀 AI Kino Bot (Inline tugmalar va Baza bilan) ishga tushdi!")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
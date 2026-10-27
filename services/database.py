import aiosqlite
from pathlib import Path

DB_PATH = Path("movie_bot.db")

async def init_db():
    """Ma'lumotlar bazasi jadvallarini yaratish"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                full_name TEXT,
                username TEXT,
                joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS search_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query_type TEXT,
                query_info TEXT,
                found_movie TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Eski jadvalda found_movie ustuni bo'lmasa qo'shib qo'yish
        try:
            await db.execute("ALTER TABLE search_history ADD COLUMN found_movie TEXT")
        except Exception:
            pass
        await db.commit()

async def add_user(user_id: int, full_name: str, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR IGNORE INTO users (user_id, full_name, username)
            VALUES (?, ?, ?)
        """, (user_id, full_name, username))
        await db.commit()

async def save_search(user_id: int, query_type: str, query_info: str, found_movie: str = "Aniqlanmadi"):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO search_history (user_id, query_type, query_info, found_movie)
            VALUES (?, ?, ?, ?)
        """, (user_id, query_type, query_info, found_movie))
        await db.commit()

async def get_user_history(user_id: int, limit: int = 5) -> list:
    """Foydalanuvchining oxirgi qidiruvlarini olish"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("""
            SELECT query_type, found_movie, timestamp 
            FROM search_history 
            WHERE user_id = ? 
            ORDER BY id DESC LIMIT ?
        """, (user_id, limit)) as cursor:
            return await cursor.fetchall()

async def get_bot_stats() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            user_count = (await cursor.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM search_history") as cursor:
            search_count = (await cursor.fetchone())[0]
        return {"users": user_count, "searches": search_count}
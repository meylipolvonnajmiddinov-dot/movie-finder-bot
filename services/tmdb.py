import aiohttp
from config import TMDB_API_KEY

async def get_movie_details(title: str, year: int = None) -> dict:
    """TMDB dan kino posteri va reytingini qidirish"""
    if not TMDB_API_KEY:
        return None

    url = "https://api.themoviedb.org/3/search/multi"
    params = {
        "api_key": TMDB_API_KEY,
        "query": title,
        "include_adult": "false"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results:
                        best = results[0]
                        poster_path = best.get("poster_path")
                        rating = best.get("vote_average", 0)
                        return {
                            "poster_url": f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None,
                            "rating": round(rating, 1) if rating else "Noma'lum"
                        }
    except Exception as e:
        print(f"TMDB Xatolik: {e}")

    return None
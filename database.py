import os
import json
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")

if DATABASE_URL:
    import asyncpg
    _pool = None

    async def get_pool():
        global _pool
        if _pool is None:
            _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
            async with _pool.acquire() as conn:
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id TEXT PRIMARY KEY,
                        user_name TEXT NOT NULL DEFAULT '',
                        score INTEGER NOT NULL DEFAULT 0,
                        click_bonus INTEGER NOT NULL DEFAULT 0,
                        auto_clicker INTEGER NOT NULL DEFAULT 0
                    )
                """)
        return _pool

    async def get_user(user_id: str) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_name, score, click_bonus, auto_clicker FROM users WHERE user_id = $1",
                user_id
            )
            if row:
                return {
                    "user_name": row["user_name"],
                    "score": row["score"],
                    "click_bonus": row["click_bonus"],
                    "auto_clicker": row["auto_clicker"],
                }
            return {"user_name": "", "score": 0, "click_bonus": 0, "auto_clicker": 0}

    async def set_user(user_id: str, user_name: str, score: int, click_bonus: int, auto_clicker: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, user_name, score, click_bonus, auto_clicker)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO UPDATE SET
                    user_name = $2, score = $3, click_bonus = $4, auto_clicker = $5
            """, user_id, user_name, score, click_bonus, auto_clicker)

    async def get_leaderboard(limit: int = 10) -> list:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_name, score FROM users ORDER BY score DESC LIMIT $1", limit
            )
            return [{"name": r["user_name"] or "Аноним", "score": r["score"]} for r in rows]

else:
    _file = Path(__file__).parent / "scores.json"
    if not _file.exists():
        _file.write_text("{}")

    def _load():
        return json.loads(_file.read_text())

    def _save(data):
        _file.write_text(json.dumps(data, indent=2))

    async def get_pool():
        pass

    async def get_user(user_id: str) -> dict:
        data = _load()
        u = data.get(user_id, {})
        return {
            "user_name": u.get("user_name", ""),
            "score": u.get("score", 0),
            "click_bonus": u.get("click_bonus", 0),
            "auto_clicker": u.get("auto_clicker", 0),
        }

    async def set_user(user_id: str, user_name: str, score: int, click_bonus: int, auto_clicker: int):
        data = _load()
        data[user_id] = {"user_name": user_name, "score": score, "click_bonus": click_bonus, "auto_clicker": auto_clicker}
        _save(data)

    async def get_leaderboard(limit: int = 10) -> list:
        data = _load()
        entries = []
        for uid, u in data.items():
            entries.append({"name": u.get("user_name", "Аноним"), "score": u.get("score", 0)})
        entries.sort(key=lambda x: -x["score"])
        return entries[:limit]

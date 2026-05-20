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
                    CREATE TABLE IF NOT EXISTS scores (
                        user_id TEXT PRIMARY KEY,
                        score INTEGER NOT NULL DEFAULT 0
                    )
                """)
        return _pool

    async def get_score(user_id: str) -> int:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT score FROM scores WHERE user_id = $1", user_id)
            return row["score"] if row else 0

    async def set_score(user_id: str, score: int):
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO scores (user_id, score) VALUES ($1, $2)
                ON CONFLICT (user_id) DO UPDATE SET score = $2
            """, user_id, score)
else:
    _file = Path(__file__).parent / "scores.json"
    if not _file.exists():
        _file.write_text("{}")

    def _load():
        return json.loads(_file.read_text())

    def _save(data):
        _file.write_text(json.dumps(data))

    async def get_pool():
        pass

    async def get_score(user_id: str) -> int:
        data = _load()
        return data.get(user_id, 0)

    async def set_score(user_id: str, score: int):
        data = _load()
        data[user_id] = score
        _save(data)

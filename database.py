import os
import json
import time
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
                        auto_clicker INTEGER NOT NULL DEFAULT 0,
                        shield_until INTEGER NOT NULL DEFAULT 0,
                        last_attack TEXT NOT NULL DEFAULT '{}'
                    )
                """)
        return _pool

    async def get_user(user_id: str) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_name, score, click_bonus, auto_clicker, shield_until, last_attack FROM users WHERE user_id = $1",
                user_id
            )
            if row:
                return {
                    "user_name": row["user_name"],
                    "score": row["score"],
                    "click_bonus": row["click_bonus"],
                    "auto_clicker": row["auto_clicker"],
                    "shield_until": row["shield_until"],
                    "last_attack": json.loads(row["last_attack"]),
                }
            return {"user_name": "", "score": 0, "click_bonus": 0, "auto_clicker": 0, "shield_until": 0, "last_attack": {}}

    async def set_user(user_id: str, user_name: str, score: int, click_bonus: int, auto_clicker: int, shield_until: int = 0, last_attack: dict = None):
        pool = await get_pool()
        if last_attack is None:
            last_attack = {}
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, user_name, score, click_bonus, auto_clicker, shield_until, last_attack)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (user_id) DO UPDATE SET
                    user_name = $2, score = $3, click_bonus = $4, auto_clicker = $5,
                    shield_until = $6, last_attack = $7
            """, user_id, user_name, score, click_bonus, auto_clicker, shield_until, json.dumps(last_attack))

    async def get_leaderboard(limit: int = 10) -> list:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, user_name, score FROM users ORDER BY score DESC LIMIT $1", limit
            )
            return [{"user_id": r["user_id"], "name": r["user_name"] or "Аноним", "score": r["score"]} for r in rows]

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
            "shield_until": u.get("shield_until", 0),
            "last_attack": u.get("last_attack", {}),
        }

    async def set_user(user_id: str, user_name: str, score: int, click_bonus: int, auto_clicker: int, shield_until: int = 0, last_attack: dict = None):
        data = _load()
        if last_attack is None:
            last_attack = {}
        data[user_id] = {
            "user_name": user_name,
            "score": score,
            "click_bonus": click_bonus,
            "auto_clicker": auto_clicker,
            "shield_until": shield_until,
            "last_attack": last_attack,
        }
        _save(data)

    async def get_leaderboard(limit: int = 10) -> list:
        data = _load()
        entries = []
        for uid, u in data.items():
            entries.append({"user_id": uid, "name": u.get("user_name", "Аноним"), "score": u.get("score", 0)})
        entries.sort(key=lambda x: -x["score"])
        return entries[:limit]

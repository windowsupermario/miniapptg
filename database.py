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
                        active_upgrades TEXT NOT NULL DEFAULT '{}',
                        last_attack TEXT NOT NULL DEFAULT '{}',
                        notifications TEXT NOT NULL DEFAULT '[]'
                    )
                """)
        return _pool

    async def get_user(user_id: str) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT user_name, score, active_upgrades, last_attack, notifications FROM users WHERE user_id = $1",
                user_id
            )
            if row:
                return {
                    "user_name": row["user_name"],
                    "score": row["score"],
                    "active_upgrades": json.loads(row["active_upgrades"]),
                    "last_attack": json.loads(row["last_attack"]),
                    "notifications": json.loads(row["notifications"]),
                }
            return {"user_name": "", "score": 0, "active_upgrades": {}, "last_attack": {}, "notifications": []}

    async def set_user(user_id: str, user_name: str, score: int, active_upgrades: dict = None, last_attack: dict = None, notifications: list = None):
        pool = await get_pool()
        if active_upgrades is None:
            active_upgrades = {}
        if last_attack is None:
            last_attack = {}
        if notifications is None:
            notifications = []
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO users (user_id, user_name, score, active_upgrades, last_attack, notifications)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id) DO UPDATE SET
                    user_name = $2, score = $3, active_upgrades = $4, last_attack = $5, notifications = $6
            """, user_id, user_name, score, json.dumps(active_upgrades), json.dumps(last_attack), json.dumps(notifications))

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
            "active_upgrades": u.get("active_upgrades", {}),
            "last_attack": u.get("last_attack", {}),
            "notifications": u.get("notifications", []),
        }

    async def set_user(user_id: str, user_name: str, score: int, active_upgrades: dict = None, last_attack: dict = None, notifications: list = None):
        data = _load()
        if active_upgrades is None:
            active_upgrades = {}
        if last_attack is None:
            last_attack = {}
        if notifications is None:
            notifications = []
        data[user_id] = {
            "user_name": user_name,
            "score": score,
            "active_upgrades": active_upgrades,
            "last_attack": last_attack,
            "notifications": notifications,
        }
        _save(data)

    async def get_leaderboard(limit: int = 10) -> list:
        data = _load()
        entries = []
        for uid, u in data.items():
            entries.append({"user_id": uid, "name": u.get("user_name", "Аноним"), "score": u.get("score", 0)})
        entries.sort(key=lambda x: -x["score"])
        return entries[:limit]

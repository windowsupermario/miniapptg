import os
import time
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from bot import start_bot, stop_bot
from database import get_pool, get_user, set_user, get_leaderboard

load_dotenv()

PORT = int(os.getenv("PORT", 8000))

UPGRADES = {
    "click_bonus_1": {"cost": 50, "field": "click_bonus", "value": 1, "name": "Лучшая ручка"},
    "click_bonus_3": {"cost": 200, "field": "click_bonus", "value": 3, "name": "Механическая рука"},
    "click_bonus_7": {"cost": 800, "field": "click_bonus", "value": 7, "name": "Робот-кликер"},
    "auto_clicker": {"cost": 300, "field": "auto_clicker", "value": 1, "name": "Автокликер"},
    "shield":      {"cost": 200, "field": "shield",     "value": 300, "name": "Щит (5 мин)"},
}

ATTACK_COST = 500
ATTACK_COOLDOWN = 900  # 15 min
SHIELD_DURATION = 300  # 5 min


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()
    yield
    await stop_bot()


app = FastAPI(title="Cookie Clicker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/")
async def index():
    return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))

@app.get("/ping")
async def ping():
    return {"ok": True, "time": int(time.time())}


@app.get("/api/user")
async def handle_get_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    notifs = state.get("notifications", [])
    if notifs:
        await set_user(user_id, state["user_name"], state["score"], state["click_bonus"], state["auto_clicker"], state["shield_until"], state["last_attack"], [])
    return {"user_id": user_id, **state, "notifications": notifs}


@app.post("/api/user")
async def handle_update_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    state = await get_user(user_id)
    await set_user(
        user_id,
        body.get("user_name", ""),
        body.get("score", 0),
        body.get("click_bonus", 0),
        body.get("auto_clicker", 0),
        state.get("shield_until", 0),
        state.get("last_attack", {}),
    )
    return {"ok": True}


@app.post("/api/upgrade/buy")
async def handle_buy_upgrade(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    upgrade_key = body.get("upgrade", "")
    upgrade = UPGRADES.get(upgrade_key)
    if not upgrade:
        return {"ok": False, "error": "Неизвестное улучшение"}

    state = await get_user(user_id)
    if state["score"] < upgrade["cost"]:
        return {"ok": False, "error": "Недостаточно очков"}

    now = int(time.time())
    new_score = state["score"] - upgrade["cost"]
    new_click_bonus = state["click_bonus"]
    new_auto_clicker = state["auto_clicker"]
    new_shield_until = state["shield_until"]

    if upgrade["field"] == "click_bonus":
        new_click_bonus += upgrade["value"]
    elif upgrade["field"] == "auto_clicker":
        if state["auto_clicker"]:
            return {"ok": False, "error": "Уже куплено"}
        new_auto_clicker = 1
    elif upgrade["field"] == "shield":
        if new_shield_until > now:
            return {"ok": False, "error": "Щит уже активен"}
        new_shield_until = now + SHIELD_DURATION

    await set_user(user_id, state["user_name"], new_score, new_click_bonus, new_auto_clicker, new_shield_until, state["last_attack"])
    return {"ok": True, "score": new_score, "click_bonus": new_click_bonus, "auto_clicker": new_auto_clicker, "shield_until": new_shield_until}


@app.post("/api/attack")
async def handle_attack(request: Request):
    attacker_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    target_id = body.get("target_id", "")

    if not target_id or target_id == attacker_id:
        return {"ok": False, "error": "Некорректная цель"}

    attacker = await get_user(attacker_id)
    target = await get_user(target_id)

    now = int(time.time())

    if attacker["score"] < ATTACK_COST:
        return {"ok": False, "error": f"Нужно {ATTACK_COST} 🍪 для атаки"}

    last_attacks = attacker.get("last_attack", {})
    last_attack_time = last_attacks.get(target_id, 0)
    if now - last_attack_time < ATTACK_COOLDOWN:
        remaining = ATTACK_COOLDOWN - (now - last_attack_time)
        return {"ok": False, "error": f"Подожди {remaining // 60} мин перед атакой на этого игрока"}

    import random
    pct = random.randint(1, 20)
    stolen = max(1, target["score"] * pct // 100)
    target_score = max(0, target["score"] - stolen)
    attacker_score = attacker["score"] - ATTACK_COST + stolen

    last_attacks[target_id] = now
    await set_user(attacker_id, attacker["user_name"], attacker_score, attacker["click_bonus"], attacker["auto_clicker"], attacker["shield_until"], last_attacks)

    target_notifs = target.get("notifications", [])
    target_notifs.append({
        "icon": "💢",
        "text": f"{attacker['user_name']} атаковал тебя и украл {stolen} 🍪!",
        "time": now,
    })
    await set_user(target_id, target["user_name"], target_score, target["click_bonus"], target["auto_clicker"], target["shield_until"], target["last_attack"], target_notifs)

    return {"ok": True, "stolen": stolen, "pct": pct, "gained": stolen, "cost": ATTACK_COST, "new_score": attacker_score}


@app.get("/api/leaderboard")
async def handle_leaderboard():
    board = await get_leaderboard(10)
    return {"leaderboard": board}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

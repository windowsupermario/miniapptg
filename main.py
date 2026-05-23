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
    "click_bonus_1": {"cost": 50, "field": "click_bonus", "value": 1, "name": "Лучшая ручка", "duration": 300},
    "click_bonus_3": {"cost": 200, "field": "click_bonus", "value": 3, "name": "Механическая рука", "duration": 300},
    "click_bonus_7": {"cost": 800, "field": "click_bonus", "value": 7, "name": "Робот-кликер", "duration": 300},
    "auto_clicker": {"cost": 300, "field": "auto_clicker", "value": 1, "name": "Автокликер", "duration": 300},
    "shield":      {"cost": 200, "field": "shield",     "value": 300, "name": "Щит (5 мин)", "duration": 300},
}

ATTACK_COST = 500
ATTACK_COOLDOWN = 900  # 15 min


def calc_derived_stats(active_upgrades):
    now = int(time.time())
    click_bonus = 0
    auto_clicker = 0
    shield_until = 0
    expired = [k for k, v in active_upgrades.items() if v <= now]
    for k in expired:
        del active_upgrades[k]
    for key, expiry in active_upgrades.items():
        upgrade = UPGRADES[key]
        if upgrade["field"] == "click_bonus":
            click_bonus += upgrade["value"]
        elif upgrade["field"] == "auto_clicker":
            auto_clicker = 1
        elif upgrade["field"] == "shield":
            shield_until = max(shield_until, expiry)
    return click_bonus, auto_clicker, shield_until


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
    click_bonus, auto_clicker, shield_until = calc_derived_stats(state["active_upgrades"])
    notifs = state.get("notifications", [])
    if notifs:
        await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"], state["last_attack"], [])
    return {"user_id": user_id, "user_name": state["user_name"], "score": state["score"], "click_bonus": click_bonus, "auto_clicker": auto_clicker, "shield_until": shield_until, "active_upgrades": state["active_upgrades"], "notifications": notifs}


@app.post("/api/user")
async def handle_update_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    state = await get_user(user_id)
    await set_user(
        user_id,
        body.get("user_name", ""),
        body.get("score", 0),
        state.get("active_upgrades", {}),
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
    active_upgrades = dict(state.get("active_upgrades", {}))
    existing_expiry = active_upgrades.get(upgrade_key)

    if existing_expiry and existing_expiry > now:
        return {"ok": False, "error": "Уже активно"}

    new_score = state["score"] - upgrade["cost"]
    active_upgrades[upgrade_key] = now + UPGRADES[upgrade_key]["duration"]

    await set_user(user_id, state["user_name"], new_score, active_upgrades, state["last_attack"])

    click_bonus, auto_clicker, shield_until = calc_derived_stats(active_upgrades)
    return {"ok": True, "score": new_score, "click_bonus": click_bonus, "auto_clicker": auto_clicker, "shield_until": shield_until, "active_upgrades": active_upgrades}


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
    break_pct = random.randint(0, 90)
    gained = stolen * (100 - break_pct) // 100
    broken = stolen - gained
    target_score = max(0, target["score"] - stolen)
    attacker_score = attacker["score"] - ATTACK_COST + gained

    last_attacks[target_id] = now
    await set_user(attacker_id, attacker["user_name"], attacker_score, attacker["active_upgrades"], last_attacks)

    target_notifs = target.get("notifications", [])
    target_notifs.append({
        "icon": "💢",
        "text": f"{attacker['user_name']} атаковал тебя и украл {stolen} 🍪!",
        "time": now,
    })
    await set_user(target_id, target["user_name"], target_score, target["active_upgrades"], target["last_attack"], target_notifs)

    return {"ok": True, "stolen": stolen, "pct": pct, "broken": broken, "break_pct": break_pct, "gained": gained, "cost": ATTACK_COST, "new_score": attacker_score}


@app.get("/api/leaderboard")
async def handle_leaderboard():
    board = await get_leaderboard(10)
    return {"leaderboard": board}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

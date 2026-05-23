import os
import time
import random
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from bot import start_bot, stop_bot
from database import get_pool, get_user, set_user, get_leaderboard, DEFAULT_EXTRA

load_dotenv()

PORT = int(os.getenv("PORT", 8000))

UPGRADES = {
    "click_bonus_1": {"cost": 50,  "field": "click_bonus", "value": 1, "name": "Лучшая ручка",    "duration": 300, "desc": "+1 к клику · 5 мин"},
    "click_bonus_3": {"cost": 200, "field": "click_bonus", "value": 3, "name": "Механическая рука","duration": 480, "desc": "+3 к клику · 8 мин", "requires": "click_bonus_1"},
    "click_bonus_7": {"cost": 800, "field": "click_bonus", "value": 7, "name": "Робот-кликер",    "duration": 900, "desc": "+7 к клику · 15 мин", "requires": "click_bonus_3"},
    "auto_clicker":  {"cost": 300, "field": "auto_clicker","value": 1, "name": "Автокликер",       "duration": 300, "desc": "+1 🍪 каждые 2 сек · 5 мин"},
    "shield":        {"cost": 200, "field": "shield",     "value": 300,"name": "Щит",             "duration": 300, "desc": "Защита от событий · 5 мин"},
    "safe":          {"cost": 400, "field": "safe",       "value": 30, "name": "Сейф",            "duration": 300, "desc": "Защищает 30% при атаке · 5 мин"},
}

ATTACK_COST = 500
ATTACK_COOLDOWN = 900
PRESTIGE_SCORE = 10000
DAILY_BONUS = 200
SPY_COST = 100
REFERRAL_BONUS = 100

GOLDEN_REWARDS = [
    {"type": "cookies", "value": 50,  "icon": "🍪", "text": "+50 🍪"},
    {"type": "cookies", "value": 100, "icon": "🍪", "text": "+100 🍪"},
    {"type": "cookies", "value": 200, "icon": "🍪", "text": "+200 🍪"},
    {"type": "boost",   "value": 1,   "icon": "⚡", "text": "x2 клика на 30 сек", "boost_key": "golden_boost", "boost_duration": 30},
]

SKINS = {
    "default": {"name": "Классическая",  "cost": 0,    "gradient": "radial-gradient(circle at 35% 35%, #f5d68a, #c8943c)", "chips": "#6b4226"},
    "choco":   {"name": "Шоколадная",    "cost": 200,  "gradient": "radial-gradient(circle at 35% 35%, #8d6e4a, #4a2c1a)", "chips": "#2d1a0a"},
    "matcha":  {"name": "Матча",         "cost": 300,  "gradient": "radial-gradient(circle at 35% 35%, #b8d9a0, #6b9b4e)", "chips": "#3d5a2e"},
    "golden":  {"name": "Золотая",       "cost": 500,  "gradient": "radial-gradient(circle at 35% 35%, #ffd700, #b8860b)", "chips": "#6b4c00"},
    "rainbow": {"name": "Радужная",      "cost": 1000, "gradient": "radial-gradient(circle at 35% 35%, #ff9a9e, #a8e6cf)", "chips": "#6b3b5a"},
    "space":   {"name": "Космическая",   "cost": 2000, "gradient": "radial-gradient(circle at 35% 35%, #5b2d8e, #1a0a3e)", "chips": "#9c6bdb"},
}

ACHIEVEMENTS = [
    {"id": "score_100",    "name": "Новичок",       "desc": "Накопить 100 🍪",        "icon": "🌱",  "check": lambda e: e["highest_score"] >= 100},
    {"id": "score_1000",   "name": "Кликер-любитель","desc": "Накопить 1000 🍪",       "icon": "🍪",  "check": lambda e: e["highest_score"] >= 1000},
    {"id": "score_5000",   "name": "Пекарня",        "desc": "Накопить 5000 🍪",       "icon": "🏭",  "check": lambda e: e["highest_score"] >= 5000},
    {"id": "score_10000",  "name": "Магнат",         "desc": "Накопить 10000 🍪",      "icon": "💰",  "check": lambda e: e["highest_score"] >= 10000},
    {"id": "attack_1",     "name": "Грабитель",      "desc": "Атаковать 1 раз",        "icon": "💢",  "check": lambda e: e["total_attacks"] >= 1},
    {"id": "attack_10",    "name": "Разбойник",      "desc": "Атаковать 10 раз",       "icon": "🗡️",  "check": lambda e: e["total_attacks"] >= 10},
    {"id": "prestige_1",   "name": "Феникс",         "desc": "Сделать престиж 1 раз",  "icon": "🔥",  "check": lambda e: e["prestige_bonus"] >= 1},
    {"id": "prestige_5",   "name": "Легенда",        "desc": "Сделать престиж 5 раз",   "icon": "🏆",  "check": lambda e: e["prestige_bonus"] >= 5},
]


def calc_derived_stats(active_upgrades):
    now = int(time.time())
    click_bonus = 0
    auto_clicker = 0
    shield_until = 0
    safe_pct = 0
    expired = [k for k, v in active_upgrades.items() if v <= now]
    for k in expired:
        del active_upgrades[k]
    for key, expiry in active_upgrades.items():
        upgrade = UPGRADES.get(key)
        if not upgrade: continue
        f = upgrade["field"]
        if f == "click_bonus":
            click_bonus += upgrade["value"]
        elif f == "auto_clicker":
            auto_clicker = 1
        elif f == "shield":
            shield_until = max(shield_until, expiry)
        elif f == "safe":
            safe_pct = max(safe_pct, upgrade["value"])
    return click_bonus, auto_clicker, shield_until, safe_pct


def calc_click_bonus(click_bonus_from_upgrades, extra):
    return click_bonus_from_upgrades + extra.get("prestige_bonus", 0)


def check_achievements(extra):
    earned = set(extra.get("achievements", []))
    new_ones = []
    for a in ACHIEVEMENTS:
        if a["id"] not in earned and a["check"](extra):
            new_ones.append(a["id"])
    if new_ones:
        earned.update(new_ones)
        extra["achievements"] = list(earned)
    return new_ones


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
async def handle_get_user(request: Request, ref: str = ""):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))

    if ref and not extra.get("referred_by") and ref != user_id:
        extra["referred_by"] = ref
        try:
            referrer = await get_user(ref)
            ref_score = referrer.get("score", 0)
            if ref_score >= 100:
                extra["referral_bonus_claimed"] = True
                state["score"] += REFERRAL_BONUS
        except:
            pass
        await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"],
                       state["last_attack"], extra=extra)
    cb, ac, su, sp = calc_derived_stats(state["active_upgrades"])
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    click_bonus = calc_click_bonus(cb, extra)

    new_achs = check_achievements(extra)
    notifs = state.get("notifications", [])

    if notifs or new_achs:
        await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"],
                       state["last_attack"], [], extra)

    return {
        "user_id": user_id,
        "user_name": state["user_name"],
        "score": state["score"],
        "click_bonus": click_bonus,
        "auto_clicker": ac,
        "shield_until": su,
        "safe_pct": sp,
        "active_upgrades": state["active_upgrades"],
        "notifications": notifs,
        "extra": extra,
        "new_achievements": new_achs,
    }


@app.post("/api/user")
async def handle_update_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    new_extra = {**extra}
    new_extra["total_clicks"] = new_extra.get("total_clicks", 0) + body.get("clicks_since_save", 0)
    new_extra["highest_score"] = max(new_extra.get("highest_score", 0), body.get("score", 0))
    await set_user(
        user_id,
        body.get("user_name", ""),
        body.get("score", 0),
        state.get("active_upgrades", {}),
        state.get("last_attack", {}),
        extra=new_extra,
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

    if "requires" in upgrade:
        req_active = state["active_upgrades"].get(upgrade["requires"], 0)
        if req_active <= int(time.time()):
            req_name = UPGRADES[upgrade["requires"]]["name"]
            return {"ok": False, "error": f"Сначала купи «{req_name}»"}

    now = int(time.time())
    active_upgrades = dict(state.get("active_upgrades", {}))
    existing_expiry = active_upgrades.get(upgrade_key)
    if existing_expiry and existing_expiry > now:
        return {"ok": False, "error": "Уже активно"}

    new_score = state["score"] - upgrade["cost"]
    active_upgrades[upgrade_key] = now + upgrade["duration"]

    extra = state.get("extra", dict(DEFAULT_EXTRA))
    await set_user(user_id, state["user_name"], new_score, active_upgrades, state["last_attack"], extra=extra)

    cb, ac, su, sp = calc_derived_stats(active_upgrades)
    click_bonus = calc_click_bonus(cb, extra)
    return {"ok": True, "score": new_score, "click_bonus": click_bonus, "auto_clicker": ac,
            "shield_until": su, "safe_pct": sp, "active_upgrades": active_upgrades}


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

    pct = random.randint(1, 20)
    stolen = max(1, target["score"] * pct // 100)

    target_extra = target.get("extra", dict(DEFAULT_EXTRA))
    _, _, _, target_safe_pct = calc_derived_stats(target["active_upgrades"])
    safe_protected = stolen * target_safe_pct // 100
    actual_stolen = stolen - safe_protected

    break_pct = random.randint(0, 90)
    gained = actual_stolen * (100 - break_pct) // 100
    broken = actual_stolen - gained

    target_score = max(0, target["score"] - actual_stolen)
    attacker_score = attacker["score"] - ATTACK_COST + gained

    last_attacks[target_id] = now
    attacker_extra = attacker.get("extra", dict(DEFAULT_EXTRA))
    attacker_extra["total_attacks"] = attacker_extra.get("total_attacks", 0) + 1
    await set_user(attacker_id, attacker["user_name"], attacker_score, attacker["active_upgrades"],
                   last_attacks, extra=attacker_extra)

    target_notifs = target.get("notifications", [])
    target_notifs.append({
        "icon": "💢",
        "text": f"{attacker['user_name']} атаковал тебя и украл {actual_stolen} 🍪!",
        "time": now,
    })
    await set_user(target_id, target["user_name"], target_score, target["active_upgrades"],
                   target["last_attack"], target_notifs, extra=target_extra)

    return {"ok": True, "stolen": actual_stolen, "pct": pct, "broken": broken, "break_pct": break_pct,
            "gained": gained, "safe_protected": safe_protected, "cost": ATTACK_COST, "new_score": attacker_score}


@app.post("/api/prestige")
async def handle_prestige(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)

    if state["score"] < PRESTIGE_SCORE:
        return {"ok": False, "error": f"Нужно {PRESTIGE_SCORE} 🍪 для престижа"}

    extra = state.get("extra", dict(DEFAULT_EXTRA))
    extra["prestige_bonus"] = extra.get("prestige_bonus", 0) + 1
    extra["highest_score"] = max(extra.get("highest_score", 0), state["score"])

    new_achs = check_achievements(extra)

    await set_user(user_id, state["user_name"], 0, {}, {}, extra=extra)

    return {"ok": True, "prestige_bonus": extra["prestige_bonus"], "new_achievements": new_achs}


@app.post("/api/daily")
async def handle_daily(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    now = int(time.time())

    today = now // 86400
    last_daily = extra.get("last_daily", 0) // 86400

    if last_daily == today:
        return {"ok": False, "error": "Уже получал сегодня"}

    extra["last_daily"] = now
    new_score = state["score"] + DAILY_BONUS
    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=extra)

    return {"ok": True, "bonus": DAILY_BONUS, "new_score": new_score}


@app.post("/api/spy")
async def handle_spy(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    target_id = body.get("target_id", "")

    if not target_id or target_id == user_id:
        return {"ok": False, "error": "Некорректная цель"}

    state = await get_user(user_id)
    if state["score"] < SPY_COST:
        return {"ok": False, "error": f"Нужно {SPY_COST} 🍪 для разведки"}

    target = await get_user(target_id)
    new_score = state["score"] - SPY_COST
    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=state.get("extra", dict(DEFAULT_EXTRA)))

    return {"ok": True, "target_name": target["user_name"], "target_score": target["score"], "new_score": new_score}


@app.post("/api/golden")
async def handle_golden(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    reward_idx = body.get("reward", 0)

    if reward_idx < 0 or reward_idx >= len(GOLDEN_REWARDS):
        return {"ok": False, "error": "Неверная награда"}

    reward = GOLDEN_REWARDS[reward_idx]
    state = await get_user(user_id)
    active_upgrades = dict(state.get("active_upgrades", {}))
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    new_score = state["score"]

    if reward["type"] == "cookies":
        new_score += reward["value"]
    elif reward["type"] == "boost":
        now = int(time.time())
        boost_key = reward["boost_key"]
        active_upgrades[boost_key] = now + reward["boost_duration"]

    await set_user(user_id, state["user_name"], new_score, active_upgrades,
                   state["last_attack"], extra=extra)

    cb, ac, su, sp = calc_derived_stats(active_upgrades)
    click_bonus = calc_click_bonus(cb, extra)
    return {"ok": True, "score": new_score, "click_bonus": click_bonus, "auto_clicker": ac,
            "shield_until": su, "safe_pct": sp, "active_upgrades": active_upgrades}


@app.post("/api/skin/buy")
async def handle_buy_skin(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    skin_key = body.get("skin", "")
    skin = SKINS.get(skin_key)
    if not skin:
        return {"ok": False, "error": "Неизвестный скин"}
    if skin["cost"] == 0:
        return {"ok": False, "error": "Уже доступен"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    owned = extra.get("owned_skins", ["default"])
    if skin_key in owned:
        return {"ok": False, "error": "Уже куплено"}

    if state["score"] < skin["cost"]:
        return {"ok": False, "error": "Недостаточно очков"}

    new_score = state["score"] - skin["cost"]
    owned.append(skin_key)
    extra["owned_skins"] = owned
    extra["current_skin"] = skin_key
    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=extra)
    return {"ok": True, "score": new_score, "current_skin": skin_key, "owned_skins": owned}


@app.get("/api/skins")
async def handle_skins_list():
    return {"skins": {k: {"name": v["name"], "cost": v["cost"]} for k, v in SKINS.items()}}


@app.get("/api/leaderboard")
async def handle_leaderboard(sort: str = "score"):
    board = await get_leaderboard(50, sort)
    return {"leaderboard": board}


@app.get("/api/referral")
async def handle_referral(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    referred = extra.get("referred_by", "")
    return {"referral_link": f"https://t.me/{(await get_bot_username())}?start=ref_{user_id}", "referred_by": referred}


async def get_bot_username():
    import os
    return os.getenv("BOT_USERNAME", "mini_app_bot")


@app.get("/api/achievements")
async def handle_achievements():
    return {"achievements": ACHIEVEMENTS}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

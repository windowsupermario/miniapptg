import os
import json
import time
import random
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from bot import start_bot, stop_bot
from database import get_pool, get_user, set_user, get_leaderboard, DEFAULT_EXTRA

PORT = int(os.getenv("PORT", 8000))

UPGRADES = {
    "click_bonus_1": {"cost": 500,  "field": "click_bonus", "value": 1, "name": "Лучшая ручка",    "duration": 300, "desc": "+1 к клику · 5 мин"},
    "click_bonus_3": {"cost": 2500, "field": "click_bonus", "value": 3, "name": "Механическая рука","duration": 480, "desc": "+3 к клику · 8 мин", "requires": "click_bonus_1"},
    "click_bonus_7": {"cost": 10000,"field": "click_bonus", "value": 7, "name": "Робот-кликер",    "duration": 900, "desc": "+7 к клику · 15 мин", "requires": "click_bonus_3"},
    "auto_clicker":  {"cost": 4000, "field": "auto_clicker","value": 1, "name": "Автокликер",       "duration": 300, "desc": "+1 🍪 каждые 2 сек · 5 мин"},
    "shield":        {"cost": 2500, "field": "shield",     "value": 300,"name": "Щит",             "duration": 300, "desc": "Защита от событий · 5 мин"},
    "safe":          {"cost": 5000, "field": "safe",       "value": 30, "name": "Сейф",            "duration": 300, "desc": "Защищает 30% при атаке · 5 мин"},
}

ATTACK_COST = 5000
ATTACK_COOLDOWN = 900
PRESTIGE_SCORE = 50000
DAILY_BONUS = 50

REFERRAL_BONUS = 100

MAX_ENERGY = 10
ENERGY_REGEN_RATE = 3
ENERGY_PER_CLICK = 1

GOLDEN_REWARDS = [
    {"type": "cookies", "value": 50,  "icon": "🍪", "text": "+50 🍪"},
    {"type": "cookies", "value": 100, "icon": "🍪", "text": "+100 🍪"},
    {"type": "cookies", "value": 200, "icon": "🍪", "text": "+200 🍪"},
    {"type": "boost",   "value": 1,   "icon": "⚡", "text": "x2 клика на 30 сек", "boost_key": "golden_boost", "boost_duration": 30},
]

GOLDEN_COOLDOWN = 25  # минимальный интервал между золотыми печеньками (сек)

SKINS = {
    "default": {"name": "Классическая",  "cost": 0,     "gradient": "radial-gradient(circle at 35% 35%, #f5d68a, #c8943c)", "chips": "#6b4226"},
    "choco":   {"name": "Шоколадная",    "cost": 2500,  "gradient": "radial-gradient(circle at 35% 35%, #8d6e4a, #4a2c1a)", "chips": "#2d1a0a"},
    "matcha":  {"name": "Матча",         "cost": 4000,  "gradient": "radial-gradient(circle at 35% 35%, #b8d9a0, #6b9b4e)", "chips": "#3d5a2e"},
    "golden":  {"name": "Золотая",       "cost": 7500,  "gradient": "radial-gradient(circle at 35% 35%, #ffd700, #b8860b)", "chips": "#6b4c00"},
    "rainbow": {"name": "Радужная",      "cost": 15000, "gradient": "radial-gradient(circle at 35% 35%, #ff9a9e, #a8e6cf)", "chips": "#6b3b5a"},
    "space":   {"name": "Космическая",   "cost": 25000, "gradient": "radial-gradient(circle at 35% 35%, #5b2d8e, #1a0a3e)", "chips": "#9c6bdb"},
}

ACHIEVEMENTS = [
    {"id": "score_100",     "name": "Новичок",           "desc": "Накопить 100 🍪",         "icon": "🌱",  "stars": 1,  "check": lambda e: e["highest_score"] >= 100},
    {"id": "score_1000",    "name": "Кликер-любитель",   "desc": "Накопить 1000 🍪",        "icon": "🍪",  "stars": 2,  "check": lambda e: e["highest_score"] >= 1000},
    {"id": "score_5000",    "name": "Пекарня",           "desc": "Накопить 5000 🍪",        "icon": "🏭",  "stars": 3,  "check": lambda e: e["highest_score"] >= 5000},
    {"id": "score_10000",   "name": "Магнат",            "desc": "Накопить 10000 🍪",       "icon": "💰",  "stars": 5,  "check": lambda e: e["highest_score"] >= 10000},
    {"id": "score_25000",   "name": "Олигарх",           "desc": "Накопить 25000 🍪",       "icon": "💎",  "stars": 8,  "check": lambda e: e["highest_score"] >= 25000},
    {"id": "score_50000",   "name": "Миллионер",         "desc": "Накопить 50000 🍪",       "icon": "👑",  "stars": 12, "check": lambda e: e["highest_score"] >= 50000},
    {"id": "score_100000",  "name": "Король печенек",    "desc": "Накопить 100000 🍪",      "icon": "🏰",  "stars": 20, "check": lambda e: e["highest_score"] >= 100000},
    {"id": "score_500000",  "name": "Император",         "desc": "Накопить 500000 🍪",      "icon": "🗿",  "stars": 50, "check": lambda e: e["highest_score"] >= 500000},
    {"id": "score_1000000", "name": "Бог печенья",       "desc": "Накопить 1 000 000 🍪",   "icon": "✨",  "stars": 100,"check": lambda e: e["highest_score"] >= 1000000},
    {"id": "attack_1",      "name": "Грабитель",         "desc": "Атаковать 1 раз",         "icon": "💢",  "stars": 1,  "check": lambda e: e["total_attacks"] >= 1},
    {"id": "attack_10",     "name": "Разбойник",         "desc": "Атаковать 10 раз",        "icon": "🗡️",  "stars": 3,  "check": lambda e: e["total_attacks"] >= 10},
    {"id": "attack_50",     "name": "Бандит",            "desc": "Атаковать 50 раз",        "icon": "💀",  "stars": 8,  "check": lambda e: e["total_attacks"] >= 50},
    {"id": "attack_100",    "name": "Мафия",             "desc": "Атаковать 100 раз",       "icon": "🔫",  "stars": 15, "check": lambda e: e["total_attacks"] >= 100},
    {"id": "prestige_1",    "name": "Феникс",            "desc": "Сделать престиж 1 раз",   "icon": "🔥",  "stars": 5,  "check": lambda e: e["prestige_bonus"] >= 1},
    {"id": "prestige_5",    "name": "Легенда",           "desc": "Сделать престиж 5 раз",   "icon": "🏆",  "stars": 10, "check": lambda e: e["prestige_bonus"] >= 5},
    {"id": "prestige_10",   "name": "Миф",              "desc": "Сделать престиж 10 раз",  "icon": "🌟",  "stars": 25, "check": lambda e: e["prestige_bonus"] >= 10},
    {"id": "prestige_25",   "name": "Бессмертный",       "desc": "Сделать престиж 25 раз",  "icon": "♾️",  "stars": 50, "check": lambda e: e["prestige_bonus"] >= 25},
    {"id": "referral_1",    "name": "Друг",              "desc": "Привести 1 друга",        "icon": "🤝",  "stars": 3,  "check": lambda e: e.get("referrals_count", 0) >= 1},
    {"id": "referral_3",    "name": "Компания",          "desc": "Привести 3 друзей",       "icon": "👥",  "stars": 5,  "check": lambda e: e.get("referrals_count", 0) >= 3},
]

LEGENDARY_UPGRADES = [
    {"id": "legend_click", "name": "✨ +5 к клику навсегда",  "cost": 50000, "min_prestige": 10, "effect": lambda e: e.update({"prestige_bonus": e.get("prestige_bonus", 0) + 5})},
    {"id": "legend_auto",  "name": "✨ Автокликер х2",        "cost": 100000, "min_prestige": 10, "effect": lambda e: e.update({"auto_speed": 1000})},
    {"id": "legend_energy","name": "✨ +50 энергии макс",     "cost": 75000, "min_prestige": 10, "effect": lambda e: e.update({"max_energy": 150})},
]

PLANETS = {
    "mars":    {"name": "Марс",    "fuel_cost": 10,   "duration": 3600, "effect": "click_bonus", "value": 2,   "desc": "+2 к клику на 1ч"},
    "venus":   {"name": "Венера",  "fuel_cost": 25,   "duration": 3600, "effect": "auto_speed",  "value": 1000,"desc": "Автокликер х2 на 1ч"},
    "jupiter": {"name": "Юпитер",  "fuel_cost": 50,   "duration": 3600, "effect": "shield",     "value": 3600, "desc": "Щит на 1ч"},
    "saturn":  {"name": "Сатурн",  "fuel_cost": 100,  "duration": 3600, "effect": "attack_bonus","value": 50,  "desc": "+50% к краже на 1ч"},
    "neptune": {"name": "Нептун",  "fuel_cost": 200,  "duration": 3600, "effect": "auto_clicker","value": 2,   "desc": "Двойной автокликер на 1ч"},
}

FUEL_COST = 250

ADMIN_ID = "7153815329"

STAR_SHOP = [
    {"id": "perm_click",  "name": "👆 +1 к клику навсегда",  "cost": 5,  "effect": lambda e: e.update({"prestige_bonus": e.get("prestige_bonus", 0) + 1})},
    {"id": "perm_attack", "name": "💢 +10% к краже",         "cost": 8,  "effect": lambda e: e.update({"attack_bonus_pct": min(e.get("attack_bonus_pct", 0) + 10, 50)})},
    {"id": "perm_start",  "name": "🚀 +1000 🍪 при старте",   "cost": 3,  "effect": lambda e: e.update({"start_bonus": e.get("start_bonus", 0) + 1000})},
    {"id": "perm_energy", "name": "⚡ +20 к макс. энергии",    "cost": 5,  "effect": lambda e: e.update({"max_energy": min(e.get("max_energy", MAX_ENERGY) + 20, 500)})},
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


def calc_energy(extra):
    now = int(time.time())
    max_e = extra.get("max_energy", MAX_ENERGY)
    energy = extra.get("energy", max_e)
    last_time = extra.get("last_energy_time", 0)
    if last_time:
        elapsed = now - last_time
        regen = elapsed * ENERGY_REGEN_RATE
        energy = min(max_e, int(energy + regen))
    extra["energy"] = energy
    extra["last_energy_time"] = now
    return energy


def apply_decay(state, extra):
    now = int(time.time())
    last_decay = extra.get("last_decay_time", 0)
    if last_decay == 0:
        extra["last_decay_time"] = now
        return state["score"]
    hours_passed = (now - last_decay) // 3600
    if hours_passed <= 0:
        return state["score"]
    score = state["score"]
    for _ in range(min(hours_passed, 24)):
        score = max(0, score - score // 100)
    extra["last_decay_time"] = now - ((now - last_decay) % 3600)
    return score


def calc_planets_bonus(active_planets):
    now = int(time.time())
    active_planets = {k: v for k, v in active_planets.items() if v > now}
    boost = {}
    for planet_key, expiry in active_planets.items():
        planet = PLANETS.get(planet_key)
        if planet:
            boost[planet["effect"]] = max(boost.get(planet["effect"], 0), planet["value"])
    return boost, active_planets


def check_achievements(extra):
    earned = set(extra.get("achievements", []))
    new_ones = []
    for a in ACHIEVEMENTS:
        if a["id"] not in earned and a["check"](extra):
            new_ones.append({"id": a["id"], "name": a["name"]})
            extra["stars"] = extra.get("stars", 0) + a.get("stars", 0)
    if new_ones:
        earned.update(a["id"] for a in new_ones)
        extra["achievements"] = list(earned)
    return new_ones


def get_effective_const():
    cfg = load_shop_config()
    c = cfg.get("_constants", {})
    return {
        "attack_cost": c.get("attack_cost", ATTACK_COST),
        "attack_cooldown": c.get("attack_cooldown", ATTACK_COOLDOWN),
        "prestige_score": c.get("prestige_score", PRESTIGE_SCORE),
        "daily_bonus": c.get("daily_bonus", DAILY_BONUS),
        "referral_bonus": c.get("referral_bonus", REFERRAL_BONUS),
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()
    yield
    stop_bot()


app = FastAPI(title="Cookie Clicker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


BROWSER_AGENTS = ["mozilla", "chrome", "safari", "webkit", "edge", "opera"]


@app.get("/")
async def index(request: Request):
    accept = request.headers.get("accept", "")
    ua = request.headers.get("user-agent", "").lower()
    if "text/html" in accept and any(b in ua for b in BROWSER_AGENTS):
        return HTMLResponse((Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8"))
    return {"ok": True}


@app.get("/ping")
async def ping():
    return {"ok": True}


@app.get("/api/user")
async def handle_get_user(request: Request, ref: str = ""):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))

    if ref and not extra.get("referred_by") and ref != user_id:
        extra["referred_by"] = ref
        try:
            ec = get_effective_const()
            rb = ec["referral_bonus"]
            referrer = await get_user(ref)
            ref_extra = referrer.get("extra", dict(DEFAULT_EXTRA))
            ref_extra["referrals_count"] = ref_extra.get("referrals_count", 0) + 1
            referrer_score = referrer.get("score", 0) + rb
            extra["referral_bonus_claimed"] = True
            state["score"] += rb // 2
            await set_user(ref, referrer["user_name"], referrer_score, referrer["active_upgrades"],
                           referrer["last_attack"], extra=ref_extra)
        except:
            pass

    decayed_score = apply_decay(state, extra)
    state["score"] = decayed_score

    start_bonus = extra.get("start_bonus", 0)
    if start_bonus > 0:
        state["score"] += start_bonus
        extra["start_bonus"] = 0

    pending = extra.get("pending_event")
    pending_event_info = None
    if pending and isinstance(pending, dict):
        elapsed = int(time.time()) - pending.get("time", 0)
        if elapsed > PENDING_EVENT_TIMEOUT:
            new_score, _ = apply_event(state["score"], pending["type"], random.randint(0, 1))
            state["score"] = new_score
            extra["pending_event"] = None
        else:
            evt = EVENTS[pending["type"]]
            pending_event_info = {
                "icon": evt["icon"],
                "text": evt["text"],
                "choices": [c["text"] for c in evt["choices"]],
            }

    calc_energy(extra)

    planets_boost, active_planets = calc_planets_bonus(extra.get("active_planets", {}))
    extra["active_planets"] = active_planets

    cb, ac, su, sp = calc_derived_stats(state["active_upgrades"])
    click_bonus = calc_click_bonus(cb, extra)

    new_achs = check_achievements(extra)
    notifs = state.get("notifications", [])

    await set_user(user_id, state["user_name"], decayed_score, state["active_upgrades"],
                   state["last_attack"], [] if (notifs or new_achs) else state.get("notifications"), extra)

    return {
        "user_id": user_id,
        "user_name": state["user_name"],
        "score": decayed_score,
        "click_bonus": click_bonus,
        "auto_clicker": ac,
        "shield_until": su,
        "safe_pct": sp,
        "active_upgrades": state["active_upgrades"],
        "notifications": notifs,
        "extra": extra,
        "new_achievements": [a["name"] for a in new_achs],
        "energy": extra.get("energy", MAX_ENERGY),
        "max_energy": extra.get("max_energy", MAX_ENERGY),
        "fuel": extra.get("fuel", 0),
        "active_planets": active_planets,
        "planets_boost": planets_boost,
        "pending_event": pending_event_info,
    }


@app.post("/api/user")
async def handle_update_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    new_extra = {**extra}
    clicks = body.get("clicks_since_save", 0)
    auto_clicks = body.get("auto_clicks_since_save", 0)
    new_extra["total_clicks"] = new_extra.get("total_clicks", 0) + clicks + auto_clicks
    new_extra["highest_score"] = max(new_extra.get("highest_score", 0), body.get("score", 0))

    new_score = body.get("score", 0)
    decayed = apply_decay({"score": new_score}, new_extra)
    if decayed != new_score:
        new_score = decayed

    max_e = new_extra.get("max_energy", MAX_ENERGY)
    energy = calc_energy(new_extra)
    energy = max(0, energy - (clicks + auto_clicks) * ENERGY_PER_CLICK)
    new_extra["energy"] = energy

    await set_user(
        user_id,
        body.get("user_name", ""),
        new_score,
        state.get("active_upgrades", {}),
        state.get("last_attack", {}),
        extra=new_extra,
    )
    return {"ok": True, "energy": energy, "max_energy": max_e, "fuel": new_extra.get("fuel", 0), "decayed": decayed != body.get("score", 0)}


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

    ec = get_effective_const()
    ac = ec["attack_cost"]
    acd = ec["attack_cooldown"]

    if attacker["score"] < ac:
        return {"ok": False, "error": f"Нужно {ac} 🍪 для атаки"}

    attacker_extra = attacker.get("extra", dict(DEFAULT_EXTRA))
    new_attacker_score = attacker["score"] - ac

    if random.random() < 0.5:
        await set_user(attacker_id, attacker["user_name"], new_attacker_score, attacker["active_upgrades"],
                       attacker["last_attack"], extra=attacker_extra)
        return {"ok": False, "error": "💢 Атака провалилась! Цель увернулась.", "cost": ac, "new_score": new_attacker_score}

    last_attacks = dict(attacker.get("last_attack", {}))
    last_attack_time = last_attacks.get(target_id, 0)
    if now - last_attack_time < acd:
        remaining = acd - (now - last_attack_time)
        await set_user(attacker_id, attacker["user_name"], new_attacker_score, attacker["active_upgrades"],
                       attacker["last_attack"], extra=attacker_extra)
        return {"ok": False, "error": f"Подожди {remaining // 60} мин перед атакой на этого игрока", "cost": ac, "new_score": new_attacker_score}

    pct = random.randint(1, 20) + attacker_extra.get("attack_bonus_pct", 0)
    active_planets = attacker_extra.get("active_planets", {})
    planet_boost, _ = calc_planets_bonus(active_planets)
    pct += planet_boost.get("attack_bonus", 0)
    stolen = max(1, target["score"] * pct // 100)

    target_extra = target.get("extra", dict(DEFAULT_EXTRA))
    _, _, _, target_safe_pct = calc_derived_stats(target["active_upgrades"])
    safe_protected = stolen * target_safe_pct // 100
    actual_stolen = stolen - safe_protected

    break_pct = random.randint(0, 30)
    broken = actual_stolen * break_pct // 100
    gained = actual_stolen - broken

    target_score = max(0, target["score"] - actual_stolen)
    attacker_score = new_attacker_score + gained

    last_attacks[target_id] = now
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
            "gained": gained, "safe_protected": safe_protected, "cost": ac, "new_score": attacker_score}


@app.post("/api/prestige")
async def handle_prestige(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    ec = get_effective_const()
    ps = ec["prestige_score"]

    if state["score"] < ps:
        return {"ok": False, "error": f"Нужно {ps} 🍪 для престижа"}

    extra = state.get("extra", dict(DEFAULT_EXTRA))
    extra["prestige_bonus"] = extra.get("prestige_bonus", 0) + 1
    extra["highest_score"] = max(extra.get("highest_score", 0), state["score"])

    new_achs = check_achievements(extra)

    await set_user(user_id, state["user_name"], 0, {}, {}, extra=extra)

    return {"ok": True, "prestige_bonus": extra["prestige_bonus"], "new_achievements": [a["name"] for a in new_achs]}


@app.post("/api/daily")
async def handle_daily(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    now = int(time.time())
    ec = get_effective_const()
    db = ec["daily_bonus"]

    today = now // 86400
    last_daily = extra.get("last_daily", 0) // 86400

    if last_daily == today:
        return {"ok": False, "error": "Уже получал сегодня"}

    extra["last_daily"] = now
    new_score = state["score"] + db
    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=extra)

    return {"ok": True, "bonus": db, "new_score": new_score}


EVENTS = [
    {  # 0: Raccoon
        "name": "Вор", "icon": "🦝", "text": "Вор лезет в кладовую!",
        "choices": [
            {"text": "Откупиться 50 🍪"},
            {"text": "Рискнуть!"},
        ]
    },
    {  # 1: Mice
        "name": "Мыши", "icon": "🐭", "text": "Мыши в кладовке!",
        "choices": [
            {"text": "Купить ловушку 30 🍪"},
            {"text": "Игнорировать"},
        ]
    },
    {  # 2: Cookie crumble
        "name": "Крошки", "icon": "💔", "text": "Печенье рассыпалось!",
        "choices": [
            {"text": "Попробовать собрать"},
            {"text": "Выбросить и забыть"},
        ]
    },
]

PENDING_EVENT_TIMEOUT = 60  # секунд — если событие не разрешили, авто-резолв


def apply_event(score: int, event_type: int, choice_idx: int) -> tuple:
    result_text = ""
    if event_type == 0:  # Raccoon
        if choice_idx == 0:
            cost = min(50, score)
            score -= cost
            if random.random() < 0.5:
                result_text = f"Вор ушёл за {cost} 🍪"
            else:
                extra = min(30, score)
                score -= extra
                result_text = f"Вор не ушёл -{cost + extra} 🍪"
        else:
            if random.random() < 0.5:
                score = max(0, score - 100)
                result_text = "-100 🍪"
            else:
                result_text = "Устоял! 👍"
    elif event_type == 1:  # Mice
        if choice_idx == 0:
            cost = min(30, score)
            score -= cost
            if random.random() < 0.5:
                result_text = f"Ловушка сработала за {cost} 🍪"
            else:
                loss = min(score, max(1, score // 10))
                score -= loss
                result_text = f"Ловушка пуста -{cost + loss} 🍪"
        else:
            loss = min(score, max(1, score // 10))
            score -= loss
            result_text = f"-{loss} 🍪"
    else:  # Cookie crumble
        would_lose = max(1, min(score, score * 15 // 100))
        if choice_idx == 0:
            if random.random() < 0.5:
                saved_pct = 0.1 + random.random() * 0.6
                saved = int(would_lose * saved_pct)
                score -= would_lose - saved
                result_text = f"Спасено {saved} 🍪 ({round(saved_pct * 100)}%)"
            else:
                score -= would_lose
                result_text = f"Рассыпалось -{would_lose} 🍪"
        else:
            score -= would_lose
            result_text = f"-{would_lose} 🍪"
    return max(0, score), result_text


@app.post("/api/event/start")
async def handle_event_start(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    now = int(time.time())

    _, _, shield_until, _ = calc_derived_stats(state["active_upgrades"])
    if shield_until > now:
        return {"ok": True, "shielded": True}

    event_type = random.randint(0, len(EVENTS) - 1)
    extra["pending_event"] = {"type": event_type, "time": now}
    await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"],
                   state["last_attack"], extra=extra)

    evt = EVENTS[event_type]
    return {
        "ok": True, "shielded": False,
        "event_type": event_type,
        "icon": evt["icon"],
        "text": evt["text"],
        "choices": [c["text"] for c in evt["choices"]],
    }


@app.post("/api/event/resolve")
async def handle_event_resolve(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    choice_idx = body.get("choice_idx", 0)

    if choice_idx < 0 or choice_idx > 1:
        return {"ok": False, "error": "Неверный выбор"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    pending = extra.get("pending_event")
    if not pending:
        return {"ok": False, "error": "Нет активного события"}

    score = state["score"]
    if score <= 50:
        extra["pending_event"] = None
        await set_user(user_id, state["user_name"], score, state["active_upgrades"],
                       state["last_attack"], extra=extra)
        return {"ok": False, "error": "Слишком мало печенек"}

    event_type = pending["type"]
    score, result_text = apply_event(score, event_type, choice_idx)

    extra["pending_event"] = None
    await set_user(user_id, state["user_name"], score, state["active_upgrades"],
                   state["last_attack"], extra=extra)

    return {"ok": True, "score": score, "result_text": result_text}


@app.post("/api/star/buy")
async def handle_star_buy(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    item_id = body.get("item", "")
    item = next((s for s in STAR_SHOP if s["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": "Неизвестный товар"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))

    if extra.get("stars", 0) < item["cost"]:
        return {"ok": False, "error": "Недостаточно ⭐"}

    extra["stars"] -= item["cost"]
    item["effect"](extra)
    await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"],
                   state["last_attack"], extra=extra)
    return {"ok": True, "stars": extra["stars"], "extra": extra}



@app.get("/api/star/shop")
async def handle_star_shop():
    return {"items": STAR_SHOP}


@app.post("/api/fuel/buy")
async def handle_fuel_buy(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    amount = max(1, body.get("amount", 1))
    cfg = get_effective_prices()
    fuel_cost = cfg["constants"]["fuel_cost"]["value"]
    total_cost = amount * fuel_cost

    state = await get_user(user_id)
    if state["score"] < total_cost:
        return {"ok": False, "error": f"Нужно {total_cost} 🍪 за {amount} ⛽"}

    extra = state.get("extra", dict(DEFAULT_EXTRA))
    new_score = state["score"] - total_cost
    extra["fuel"] = extra.get("fuel", 0) + amount

    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=extra)
    return {"ok": True, "score": new_score, "fuel": extra["fuel"]}


@app.post("/api/golden")
async def handle_golden(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    reward_idx = body.get("reward", 0)

    if reward_idx < 0 or reward_idx >= len(GOLDEN_REWARDS):
        return {"ok": False, "error": "Неверная награда"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    now = int(time.time())

    last_golden = extra.get("last_golden_time", 0)
    if now - last_golden < GOLDEN_COOLDOWN:
        return {"ok": False, "error": "Слишком часто"}

    reward = GOLDEN_REWARDS[reward_idx]
    active_upgrades = dict(state.get("active_upgrades", {}))
    new_score = state["score"]
    extra["last_golden_time"] = now

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
    board = await get_leaderboard(10, sort)
    return {"leaderboard": board}


@app.get("/api/referral")
async def handle_referral(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    referred = extra.get("referred_by", "")
    return {"referral_link": f"https://t.me/sfarenabot?start=ref_{user_id}", "referred_by": referred}


async def get_bot_username():
    return "sfarenabot"


@app.get("/api/achievements")
async def handle_achievements():
    return {"achievements": ACHIEVEMENTS}


@app.post("/api/planet/travel")
async def handle_planet_travel(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    planet_key = body.get("planet", "")
    planet = PLANETS.get(planet_key)
    if not planet:
        return {"ok": False, "error": "Неизвестная планета"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))
    now = int(time.time())

    fuel = extra.get("fuel", 0)
    if fuel < planet["fuel_cost"]:
        return {"ok": False, "error": f"Нужно {planet['fuel_cost']} ⛽ топлива"}

    active_planets = dict(extra.get("active_planets", {}))
    existing = active_planets.get(planet_key, 0)
    if existing > now:
        return {"ok": False, "error": "Уже на этой планете"}

    active_planets[planet_key] = now + planet["duration"]
    extra["active_planets"] = active_planets
    extra["fuel"] = fuel - planet["fuel_cost"]

    planets_boost, cleaned = calc_planets_bonus(active_planets)
    extra["active_planets"] = cleaned

    await set_user(user_id, state["user_name"], state["score"], state["active_upgrades"],
                   state["last_attack"], extra=extra)
    return {"ok": True, "fuel": extra["fuel"], "active_planets": cleaned, "planets_boost": planets_boost,
            "planet_name": planet["name"], "expires": now + planet["duration"]}


@app.get("/api/legend/shop")
async def handle_legend_shop():
    return {"items": LEGENDARY_UPGRADES}


@app.post("/api/legend/buy")
async def handle_legend_buy(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    item_id = body.get("item", "")
    item = next((s for s in LEGENDARY_UPGRADES if s["id"] == item_id), None)
    if not item:
        return {"ok": False, "error": "Неизвестный апгрейд"}

    state = await get_user(user_id)
    extra = state.get("extra", dict(DEFAULT_EXTRA))

    if extra.get("prestige_bonus", 0) < item["min_prestige"]:
        return {"ok": False, "error": f"Нужно {item['min_prestige']} престижей"}

    if item_id in extra.get("legendary_bought", []):
        return {"ok": False, "error": "Уже куплено"}

    if state["score"] < item["cost"]:
        return {"ok": False, "error": "Недостаточно 🍪"}

    new_score = state["score"] - item["cost"]
    bought = extra.get("legendary_bought", [])
    bought.append(item_id)
    extra["legendary_bought"] = bought
    item["effect"](extra)

    await set_user(user_id, state["user_name"], new_score, state["active_upgrades"],
                   state["last_attack"], extra=extra)
    return {"ok": True, "score": new_score, "extra": extra}



SHOP_CONFIG_FILE = Path(__file__).parent / "shop_config.json"


def load_shop_config():
    try:
        return json.loads(SHOP_CONFIG_FILE.read_text())
    except:
        return {}


def save_shop_config(data: dict):
    SHOP_CONFIG_FILE.write_text(json.dumps(data, indent=2))


def merge_shop_overrides(overrides: dict) -> dict:
    result = {}
    for k, v in UPGRADES.items():
        item = dict(v)
        if k in overrides:
            item.update(overrides[k])
        result[k] = item
    return result


@app.get("/api/shop/upgrades")
async def handle_shop_upgrades():
    overrides = load_shop_config()
    return {"upgrades": merge_shop_overrides(overrides)}


@app.get("/api/admin/shop")
async def handle_admin_get_shop(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    overrides = load_shop_config()
    return {"ok": True, "upgrades": merge_shop_overrides(overrides)}


@app.post("/api/admin/shop/price")
async def handle_admin_set_price(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    body = await request.json()
    key = body.get("key", "")
    if key not in UPGRADES:
        return {"ok": False, "error": "Неизвестный товар"}
    try:
        overrides = load_shop_config()
        if key not in overrides:
            overrides[key] = {}
        if "cost" in body:
            cost = int(body["cost"])
            if cost < 0:
                return {"ok": False, "error": "Цена не может быть отрицательной"}
            overrides[key]["cost"] = cost
        if "name" in body:
            overrides[key]["name"] = str(body["name"])
        if "duration" in body:
            duration = int(body["duration"])
            if duration < 10:
                return {"ok": False, "error": "Длительность минимум 10 секунд"}
            overrides[key]["duration"] = duration
        save_shop_config(overrides)
        return {"ok": True, "upgrades": merge_shop_overrides(overrides)}
    except (ValueError, TypeError):
        return {"ok": False, "error": "Некорректное значение"}


@app.post("/api/admin/user/balance")
async def handle_admin_user_balance(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    body = await request.json()
    target_id = str(body.get("user_id", ""))
    new_score = int(body.get("score", 0))
    if not target_id:
        return {"ok": False, "error": "Не указан user_id"}
    try:
        state = await get_user(target_id)
        await set_user(target_id, state["user_name"], new_score, state["active_upgrades"],
                       state["last_attack"], extra=state.get("extra", dict(DEFAULT_EXTRA)))
        return {"ok": True, "user_id": target_id, "new_score": new_score}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/admin/user/reset")
async def handle_admin_user_reset(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    body = await request.json()
    target_id = str(body.get("user_id", ""))
    if not target_id:
        return {"ok": False, "error": "Не указан user_id"}
    try:
        await set_user(target_id, "", 0, {}, {}, [], dict(DEFAULT_EXTRA))
        return {"ok": True, "user_id": target_id, "message": "Прогресс сброшен"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def get_effective_prices():
    overrides = load_shop_config()
    result = {}

    result["upgrades"] = {}
    for k, v in UPGRADES.items():
        item = dict(v)
        if k in overrides:
            item.update(overrides[k])
        result["upgrades"][k] = item

    result["skins"] = {}
    for k, v in SKINS.items():
        item = dict(v)
        sk = overrides.get("_skins", {}).get(k, {})
        item.update(sk)
        result["skins"][k] = item

    result["star_shop"] = []
    for item in STAR_SHOP:
        i = dict(item)
        sk = overrides.get("_star_shop", {}).get(item["id"], {})
        i.update(sk)
        result["star_shop"].append(i)

    result["planets"] = {}
    for k, v in PLANETS.items():
        item = dict(v)
        sk = overrides.get("_planets", {}).get(k, {})
        item.update(sk)
        result["planets"][k] = item

    result["legendary"] = []
    for item in LEGENDARY_UPGRADES:
        i = dict(item)
        sk = overrides.get("_legendary", {}).get(item["id"], {})
        i.update(sk)
        result["legendary"].append(i)

    result["constants"] = {
        "fuel_cost": {"value": FUEL_COST, "label": "Цена топлива (🍪)"},
        "attack_cost": {"value": ATTACK_COST, "label": "Стоимость атаки (🍪)"},
        "attack_cooldown": {"value": ATTACK_COOLDOWN, "label": "Кд атаки (сек)"},
        "prestige_score": {"value": PRESTIGE_SCORE, "label": "Престиж (🍪)"},
        "daily_bonus": {"value": DAILY_BONUS, "label": "Дневной бонус (🍪)"},
        "referral_bonus": {"value": REFERRAL_BONUS, "label": "Бонус за реферала (🍪)"},
    }
    const_overrides = overrides.get("_constants", {})
    for k in result["constants"]:
        if k in const_overrides:
            result["constants"][k]["value"] = const_overrides[k]

    return result


@app.get("/api/admin/all-config")
async def handle_admin_all_config(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    return {"ok": True, "config": get_effective_prices()}


@app.post("/api/admin/set-config")
async def handle_admin_set_config(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", ""))
    if user_id != ADMIN_ID:
        return {"ok": False, "error": "Доступ запрещён"}
    body = await request.json()
    category = body.get("category", "")
    key = body.get("key", "")
    field = body.get("field", "")
    value = body.get("value")

    overrides = load_shop_config()

    if category == "upgrades":
        if key not in UPGRADES:
            return {"ok": False, "error": "Неизвестный товар"}
        if key not in overrides:
            overrides[key] = {}
        overrides[key][field] = value
        save_shop_config(overrides)
        return {"ok": True, "config": get_effective_prices()}

    if category == "constants":
        if key not in ["fuel_cost", "attack_cost", "attack_cooldown", "prestige_score", "daily_bonus", "referral_bonus"]:
            return {"ok": False, "error": "Неизвестная константа"}
        if "_constants" not in overrides:
            overrides["_constants"] = {}
        overrides["_constants"][key] = int(value)
        save_shop_config(overrides)
        return {"ok": True, "config": get_effective_prices()}

    cat_map = {
        "skins": ("_skins", SKINS),
        "planets": ("_planets", PLANETS),
    }
    if category in cat_map:
        cat_key, source = cat_map[category]
        if key not in source:
            return {"ok": False, "error": "Неизвестный ключ"}
        if cat_key not in overrides:
            overrides[cat_key] = {}
        if key not in overrides[cat_key]:
            overrides[cat_key][key] = {}
        overrides[cat_key][key][field] = int(value)
        save_shop_config(overrides)
        return {"ok": True, "config": get_effective_prices()}

    if category in ("star_shop", "legendary"):
        cat_key = "_" + category
        source = STAR_SHOP if category == "star_shop" else LEGENDARY_UPGRADES
        item_ids = [i["id"] for i in source]
        if key not in item_ids:
            return {"ok": False, "error": "Неизвестный ключ"}
        if cat_key not in overrides:
            overrides[cat_key] = {}
        if key not in overrides[cat_key]:
            overrides[cat_key][key] = {}
        overrides[cat_key][key][field] = int(value)
        save_shop_config(overrides)
        return {"ok": True, "config": get_effective_prices()}

    return {"ok": False, "error": "Неизвестная категория"}


@app.get("/api/shop/all")
async def handle_shop_all():
    return {"ok": True, "config": get_effective_prices()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

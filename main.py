import os
import asyncio
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
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_pool()
    t = threading.Thread(target=start_bot, daemon=True)
    t.start()
    yield
    await stop_bot()


app = FastAPI(title="Cookie Clicker", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")


@app.get("/api/user")
async def handle_get_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    state = await get_user(user_id)
    return {"user_id": user_id, **state}


@app.post("/api/user")
async def handle_update_user(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    await set_user(
        user_id,
        body.get("user_name", ""),
        body.get("score", 0),
        body.get("click_bonus", 0),
        body.get("auto_clicker", 0),
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

    new_score = state["score"] - upgrade["cost"]
    new_click_bonus = state["click_bonus"]
    new_auto_clicker = state["auto_clicker"]

    if upgrade["field"] == "click_bonus":
        new_click_bonus += upgrade["value"]
    elif upgrade["field"] == "auto_clicker":
        if state["auto_clicker"]:
            return {"ok": False, "error": "Уже куплено"}
        new_auto_clicker = 1

    await set_user(user_id, state["user_name"], new_score, new_click_bonus, new_auto_clicker)
    return {"ok": True, "score": new_score, "click_bonus": new_click_bonus, "auto_clicker": new_auto_clicker}


@app.get("/api/leaderboard")
async def handle_leaderboard():
    board = await get_leaderboard(10)
    return {"leaderboard": board}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

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
from database import get_pool, get_score, set_score

load_dotenv()

PORT = int(os.getenv("PORT", 8000))


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


@app.get("/api/score")
async def handle_get_score(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    score = await get_score(user_id)
    return {"user_id": user_id, "score": score}


@app.post("/api/score")
async def handle_update_score(request: Request):
    user_id = str(request.headers.get("x-telegram-user-id", "guest"))
    body = await request.json()
    await set_score(user_id, body.get("score", 0))
    return {"ok": True, "score": body.get("score", 0)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=PORT)

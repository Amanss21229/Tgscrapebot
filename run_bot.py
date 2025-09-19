# run_bot.py  (webhook version using FastAPI + aiogram)
import os
import logging
import asyncio

from fastapi import FastAPI, Request
from aiogram import Bot, Dispatcher
from aiogram.types import Update
# import and register your handlers/blueprints here
# from group_transfer_bot import setup_handlers  # example

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# the public URL where Render will expose your app, e.g. "https://your-app.onrender.com"
WEBHOOK_BASE = os.getenv("WEBHOOK_BASE_URL")
if not WEBHOOK_BASE:
    raise RuntimeError("WEBHOOK_BASE_URL must be set to your Render public URL, e.g. https://my-app.onrender.com")

WEBHOOK_PATH = f"/webhook/{BOT_TOKEN}"
WEBHOOK_URL = WEBHOOK_BASE.rstrip("/") + WEBHOOK_PATH

# Setup bot & dispatcher
bot = Bot(token=BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher()

# Import and register your handlers here (must register onto 'dp')
# Example: if your group_transfer_bot.py exposes a function to register handlers:
# from group_transfer_bot import register_handlers
# register_handlers(dp, bot)   # adapt to your repo structure
# If your code registers handlers when importing, import it here:
import group_transfer_bot  # ensure that this registers onto dp or expose register function

app = FastAPI()

@app.post(WEBHOOK_PATH)
async def telegram_webhook(request: Request):
    data = await request.json()
    update = Update(**data)
    await dp.process_update(update)
    return {"ok": True}

@app.on_event("startup")
async def on_startup():
    # set webhook on startup
    await bot.set_webhook(WEBHOOK_URL)
    logger.info("Webhook set to %s", WEBHOOK_URL)

@app.on_event("shutdown")
async def on_shutdown():
    await bot.delete_webhook()
    await bot.session.close()
    logger.info("Shutdown: webhooks removed")

# expose the FastAPI app as 'app' for Gunicorn/UVicorn

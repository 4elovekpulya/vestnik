import asyncio
import os
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
)
from aiogram.filters import Command

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== НАСТРОЙКИ =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
# ====================

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

# ===== БАЗА ДАННЫХ =====
db = sqlite3.connect("concerts.db")
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS concerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    datetime TEXT,
    description TEXT,
    image_file_id TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER,
    concert_id INTEGER,
    subscribed_at TEXT,
    PRIMARY KEY (user_id, concert_id)
)
""")

db.commit()

# ===== КНОПКИ =====
def concert_keyboard(concert_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("Напомнить", callback_data=f"sub:{concert_id}"),
                InlineKeyboardButton("Отписаться", callback_data=f"unsub:{concert_id}")
            ]
        ]
    )

# ===== ВСПОМОГАТЕЛЬНО =====
def parse_dt(date_str, time_str):
    return datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MOSCOW_TZ)

async def send

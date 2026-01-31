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
db = sqlite3.connect("concerts.db", check_same_thread=False)
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
                InlineKeyboardButton(
                    text="Напомнить",
                    callback_data=f"sub:{concert_id}"
                ),
                InlineKeyboardButton(
                    text="Отписаться",
                    callback_data=f"unsub:{concert_id}"
                )
            ]
        ]
    )

# ===== ВСПОМОГАТЕЛЬНО =====
def parse_dt(date_str, time_str):
    return datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MOSCOW_TZ)

async def send_reminder(concert_id: int, text: str):
    cur.execute(
        "SELECT user_id FROM subscriptions WHERE concert_id = ?",
        (concert_id,)
    )
    users = cur.fetchall()

    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text)
        except Exception:
            pass

# ===== КОМАНДЫ =====
@dp.message(Command("start"))
async def start(message: Message):
    cur.execute("SELECT id, datetime, description FROM concerts ORDER BY datetime")
    concerts = cur.fetchall()

    if not concerts:
        await message.answer("Пока нет запланированных концертов.")
        return

    for concert_id, dt_str, desc in concerts:
        dt = datetime.fromisoformat(dt_str)
        text = f"{desc}\n\n📅 {dt.strftime('%d.%m.%Y %H:%M')}"
        await message.answer(text, reply_markup=concert_keyboard(concert_id))

@dp.message(Command("setconcert"))
async def set_concert(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /setconcert YYYY-MM-DD HH:MM Описание")
        return

    date_str, time_str = parts[1].split()
    description = parts[2]

    dt = parse_dt(date_str, time_str)

    cur.execute(
        "INSERT INTO concerts (datetime, description) VALUES (?, ?)",
        (dt.isoformat(), description)
    )
    concert_id = cur.lastrowid
    db.commit()

    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt.replace(hour=11, minute=0),
        args=[concert_id, f"Сегодня концерт!\n\n{description}"]
    )

    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt - timedelta(hours=1, minutes=30),
        args=[concert_id, f"Скоро концерт!\n\n{description}"]
    )

    await message.answer("Концерт добавлен и напоминания запланированы.")

# ===== CALLBACKS =====
@dp.callback_query(F.data.startswith("sub:"))
async def subscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (call.from_user.id, concert_id, datetime.now(MOSCOW_TZ).isoformat())
    )
    db.commit()

    await call.answer("Напоминание включено", show_alert=True)

@dp.callback_query(F.data.startswith("unsub:"))
async def unsubscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "DELETE FROM subscriptions WHERE user_id = ? AND concert_id = ?",
        (call.from_user.id, concert_id)
    )
    db.commit()

    await call.answer("Вы отписались", show_alert=True)

# ===== ЗАПУСК =====
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

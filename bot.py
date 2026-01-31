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

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MOSCOW_TZ = ZoneInfo("Europe/Moscow")

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

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

# ---------- KEYBOARDS ----------
def user_keyboard(cid: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton("Напомнить", callback_data=f"sub:{cid}"),
            InlineKeyboardButton("Отписаться", callback_data=f"unsub:{cid}")
        ]]
    )

def admin_concerts_keyboard():
    cur.execute("SELECT id, datetime, description FROM concerts ORDER BY datetime")
    rows = cur.fetchall()

    if not rows:
        return None

    kb = []
    for cid, dt, desc in rows:
        dt = datetime.fromisoformat(dt)
        kb.append([
            InlineKeyboardButton(
                f"{dt.strftime('%d.%m %H:%M')} — {desc[:20]}",
                callback_data=f"admin:concert:{cid}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=kb)

# ---------- HELPERS ----------
def parse_dt(date_str, time_str):
    return datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MOSCOW_TZ)

async def send_reminder(cid: int, title: str):
    cur.execute("SELECT description, image_file_id FROM concerts WHERE id=?", (cid,))
    row = cur.fetchone()
    if not row:
        return

    desc, image = row
    text = f"{title}\n\n{desc}"

    cur.execute("SELECT user_id FROM subscriptions WHERE concert_id=?", (cid,))
    users = cur.fetchall()

    for (uid,) in users:
        try:
            if image:
                await bot.send_photo(uid, image, caption=text)
            else:
                await bot.send_message(uid, text)
        except:
            pass

# ---------- USER ----------
@dp.message(Command("start"))
async def start(message: Message):
    cur.execute("SELECT id, datetime, description, image_file_id FROM concerts ORDER BY datetime")
    concerts = cur.fetchall()

    if not concerts:
        await message.answer("Пока нет запланированных концертов.")
        return

    for cid, dt, desc, image in concerts:
        dt = datetime.fromisoformat(dt)
        text = f"{dt.strftime('%d.%m.%Y %H:%M')}\n{desc}"
        if image:
            await message.answer_photo(image, caption=text, reply_markup=user_keyboard(cid))
        else:
            await message.answer(text, reply_markup=user_keyboard(cid))

# ---------- ADMIN ----------
@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    kb = admin_concerts_keyboard()
    if not kb:
        await message.answer("Концертов пока нет. Добавь первый через /setconcert")
        return

    await message.answer("Выбери концерт:", reply_markup=kb)

@dp.message(Command("setconcert"))
async def setconcert(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Формат: /setconcert YYYY-MM-DD HH:MM Описание")
        return

    dt = parse_dt(parts[1], parts[2])
    desc = parts[3]

    cur.execute(
        "INSERT INTO concerts (datetime, description) VALUES (?, ?)",
        (dt.isoformat(), desc)
    )
    cid = cur.lastrowid
    db.commit()

    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt.replace(hour=11, minute=0),
        args=[cid, "Сегодня концерт"]
    )
    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt - timedelta(hours=1, minutes=30),
        args=[cid, "До концерта осталось 1,5 часа"]
    )

    await message.answer("Концерт добавлен.")

# ---------- SUBSCRIBE ----------
@dp.callback_query(F.data.startswith("sub:"))
async def sub(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (call.from_user.id, cid, datetime.now(MOSCOW_TZ).isoformat())
    )
    db.commit()
    await call.answer("Готово", show_alert=True)

@dp.callback_query(F.data.startswith("unsub:"))
async def unsub(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    cur.execute(
        "DELETE FROM subscriptions WHERE user_id=? AND concert_id=?",
        (call.from_user.id, cid)
    )
    db.commit()
    await call.answer("Вы отписались", show_alert=True)

# ---------- START ----------
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

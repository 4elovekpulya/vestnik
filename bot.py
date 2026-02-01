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
def select_concert_keyboard(concert_id: int, title: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"concert:{concert_id}")]
        ]
    )

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

def now_moscow():
    return datetime.now(MOSCOW_TZ)

def get_subscribers_count(concert_id: int) -> int:
    cur.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE concert_id = ?",
        (concert_id,)
    )
    return cur.fetchone()[0]

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
    cur.execute(
        "SELECT id, datetime, description FROM concerts "
        "WHERE datetime > ? "
        "ORDER BY datetime",
        (now_moscow().isoformat(),)
    )
    concerts = cur.fetchall()

    if not concerts:
        await message.answer("Пока нет запланированных концертов.")
        return

    await message.answer("Выбери концерт:")

    for concert_id, dt_str, desc in concerts:
        await message.answer(
            desc,
            reply_markup=select_concert_keyboard(concert_id, desc)
        )

@dp.message(Command("setconcert"))
async def set_concert(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    parts = message.text.split(maxsplit=3)
    if len(parts) < 4:
        await message.answer("Формат: /setconcert YYYY-MM-DD HH:MM Описание")
        return

    date_str, time_str, description = parts[1], parts[2], parts[3]

    try:
        dt = parse_dt(date_str, time_str)
    except ValueError:
        await message.answer("Ошибка даты или времени.")
        return

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
        run_date=dt - timedelta(minutes=90),
        args=[concert_id, f"Скоро концерт!\n\n{description}"]
    )

    await message.answer(
        "Концерт добавлен.\n\nТеперь пришли картинку ответом на это сообщение."
    )

@dp.message(F.photo)
async def save_image(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cur.execute(
        "SELECT id FROM concerts ORDER BY id DESC LIMIT 1"
    )
    row = cur.fetchone()

    if not row:
        await message.answer("Нет концерта, к которому можно привязать картинку.")
        return

    concert_id = row[0]
    photo = message.photo[-1]

    cur.execute(
        "UPDATE concerts SET image_file_id = ? WHERE id = ?",
        (photo.file_id, concert_id)
    )
    db.commit()

    await message.answer("Картинка сохранена для последнего концерта.")

# ===== CALLBACKS =====
@dp.callback_query(F.data.startswith("concert:"))
async def show_concert(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "SELECT datetime, description, image_file_id FROM concerts WHERE id = ?",
        (concert_id,)
    )
    row = cur.fetchone()

    if not row:
        await call.answer("Концерт не найден", show_alert=True)
        return

    dt_str, desc, image_id = row
    dt = datetime.fromisoformat(dt_str)

    if dt < now_moscow():
        await call.answer("Этот концерт уже прошёл", show_alert=True)
        return

    count = get_subscribers_count(concert_id)

    text = (
        f"{desc}\n\n"
        f"📅 {dt.strftime('%d.%m.%Y %H:%M')}\n"
        f"👥 Подписались: {count}"
    )

    if image_id:
        await call.message.answer_photo(
            photo=image_id,
            caption=text,
            reply_markup=concert_keyboard(concert_id)
        )
    else:
        await call.message.answer(
            text,
            reply_markup=concert_keyboard(concert_id)
        )

    await call.answer()

@dp.callback_query(F.data.startswith("sub:"))
async def subscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "SELECT datetime FROM concerts WHERE id = ?",
        (concert_id,)
    )
    row = cur.fetchone()

    if not row:
        await call.answer("Концерт не найден", show_alert=True)
        return

    dt = datetime.fromisoformat(row[0])
    if dt < now_moscow():
        await call.answer("Этот концерт уже прошёл", show_alert=True)
        return

    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (call.from_user.id, concert_id, now_moscow().isoformat())
    )
    db.commit()

    count = get_subscribers_count(concert_id)

    await call.answer(
        f"Напоминание включено. Подписались: {count}",
        show_alert=True
    )

@dp.callback_query(F.data.startswith("unsub:"))
async def unsubscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "DELETE FROM subscriptions WHERE user_id = ? AND concert_id = ?",
        (call.from_user.id, concert_id)
    )
    db.commit()

    count = get_subscribers_count(concert_id)

    await call.answer(
        f"Вы отписались. Подписались: {count}",
        show_alert=True
    )

# ===== ЗАПУСК =====
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

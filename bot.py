import asyncio
import sqlite3
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    FSInputFile,
)
from aiogram.filters import Command

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ===== НАСТРОЙКИ =====
TOKEN = "8566906143:AAEnKS_c7-oa7DxOr4fOra36CSooWn674GE"
ADMIN_ID = 534395347
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
# ====================

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

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

# ---------- КНОПКИ ----------
def concert_keyboard(concert_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("Напомнить", callback_data=f"sub:{concert_id}"),
                InlineKeyboardButton("Отписаться", callback_data=f"unsub:{concert_id}")
            ]
        ]
    )

# ---------- ВСПОМОГАТЕЛЬНО ----------
def parse_dt(date_str, time_str):
    return datetime.strptime(
        f"{date_str} {time_str}", "%Y-%m-%d %H:%M"
    ).replace(tzinfo=MOSCOW_TZ)

def schedule_concert(concert_id, dt):
    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt.replace(hour=11, minute=0),
        args=[concert_id, "Сегодня концерт"]
    )
    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=dt - timedelta(hours=1, minutes=30),
        args=[concert_id, "До концерта осталось 1,5 часа"]
    )

async def send_reminder(concert_id, title):
    cur.execute("SELECT description, image_file_id FROM concerts WHERE id=?", (concert_id,))
    desc, image = cur.fetchone()

    cur.execute("SELECT user_id FROM subscriptions WHERE concert_id=?", (concert_id,))
    users = cur.fetchall()

    for (uid,) in users:
        try:
            if image:
                await bot.send_photo(uid, image, caption=f"{title}\n\n{desc}")
            else:
                await bot.send_message(uid, f"{title}\n\n{desc}")
        except:
            pass

# ---------- КОМАНДЫ ----------
@dp.message(Command("start"))
async def start(message: Message):
    cur.execute("SELECT id, datetime, description, image_file_id FROM concerts ORDER BY datetime")
    for cid, dt, desc, image in cur.fetchall():
        dt = datetime.fromisoformat(dt)
        text = f"{dt.strftime('%d.%m.%Y %H:%M')}\n{desc}"
        if image:
            await message.answer_photo(image, caption=text, reply_markup=concert_keyboard(cid))
        else:
            await message.answer(text, reply_markup=concert_keyboard(cid))

@dp.message(Command("setconcert"))
async def setconcert(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    parts = message.text.split()
    try:
        if len(parts) == 3:
            dt = parse_dt(parts[1], parts[2])
            cur.execute("INSERT INTO concerts (datetime, description) VALUES (?, '')", (dt.isoformat(),))
            db.commit()
            cid = cur.lastrowid
        elif len(parts) == 4:
            cid = int(parts[1])
            dt = parse_dt(parts[2], parts[3])
            cur.execute("UPDATE concerts SET datetime=? WHERE id=?", (dt.isoformat(), cid))
            db.commit()
        else:
            raise ValueError
        schedule_concert(cid, dt)
        await message.answer("Концерт сохранён.")
    except:
        await message.answer("Формат:\n/setconcert [id] YYYY-MM-DD HH:MM")

@dp.message(Command("edittext"))
async def edittext(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    try:
        _, cid, *text = message.text.split()
        cur.execute("UPDATE concerts SET description=? WHERE id=?", (" ".join(text), int(cid)))
        db.commit()
        await message.answer("Текст обновлён.")
    except:
        await message.answer("Формат:\n/edittext ID текст")

@dp.message(Command("preview"))
async def preview(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    cid = int(message.text.split()[1])
    cur.execute("SELECT datetime, description, image_file_id FROM concerts WHERE id=?", (cid,))
    dt, desc, image = cur.fetchone()
    dt = datetime.fromisoformat(dt)
    text = f"{dt.strftime('%d.%m.%Y %H:%M')}\n{desc}"
    if image:
        await message.answer_photo(image, caption=text)
    else:
        await message.answer(text)

@dp.message(F.photo & F.caption.startswith("/setimage"))
async def setimage(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    cid = int(message.caption.split()[1])
    file_id = message.photo[-1].file_id
    cur.execute("UPDATE concerts SET image_file_id=? WHERE id=?", (file_id, cid))
    db.commit()
    await message.answer("Изображение сохранено.")

# ---------- ПОДПИСКИ ----------
@dp.callback_query(F.data.startswith("sub:"))
async def sub(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (callback.from_user.id, cid, datetime.now(MOSCOW_TZ).isoformat())
    )
    db.commit()
    await callback.answer("Вы подписаны.")

@dp.callback_query(F.data.startswith("unsub:"))
async def unsub(callback: CallbackQuery):
    cid = int(callback.data.split(":")[1])
    cur.execute("DELETE FROM subscriptions WHERE user_id=? AND concert_id=?", (callback.from_user.id, cid))
    db.commit()
    await callback.answer("Вы отписались.")

# ---------- ЗАПУСК ----------
async def main():
    cur.execute("SELECT id, datetime FROM concerts")
    for cid, dt in cur.fetchall():
        schedule_concert(cid, datetime.fromisoformat(dt))
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

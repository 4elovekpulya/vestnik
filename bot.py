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

# ===== КНОПКИ =====
def user_keyboard(concert_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton("Напомнить", callback_data=f"sub:{concert_id}"),
                InlineKeyboardButton("Отписаться", callback_data=f"unsub:{concert_id}")
            ]
        ]
    )

def admin_concerts_keyboard():
    cur.execute("SELECT id, datetime, description FROM concerts ORDER BY datetime")
    rows = cur.fetchall()

    buttons = []
    for cid, dt, desc in rows:
        dt = datetime.fromisoformat(dt)
        buttons.append([
            InlineKeyboardButton(
                f"{dt.strftime('%d.%m %H:%M')} — {desc[:20]}",
                callback_data=f"admin:concert:{cid}"
            )
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)

def admin_actions_keyboard(concert_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton("✏️ Изменить текст", callback_data=f"admin:text:{concert_id}")],
            [InlineKeyboardButton("🖼 Изменить картинку", callback_data=f"admin:image:{concert_id}")],
            [InlineKeyboardButton("👁 Предпросмотр", callback_data=f"admin:preview:{concert_id}")]
        ]
    )

# ===== USER =====
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

# ===== ADMIN =====
@dp.message(Command("admin"))
async def admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    await message.answer(
        "Выбери концерт:",
        reply_markup=admin_concerts_keyboard()
    )

@dp.callback_query(F.data.startswith("admin:concert:"))
async def admin_select_concert(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    await call.message.answer(
        "Действия с концертом:",
        reply_markup=admin_actions_keyboard(cid)
    )

@dp.callback_query(F.data.startswith("admin:preview:"))
async def admin_preview(call: CallbackQuery):
    cid = int(call.data.split(":")[2])
    cur.execute("SELECT datetime, description, image_file_id FROM concerts WHERE id=?", (cid,))
    dt, desc, image = cur.fetchone()
    dt = datetime.fromisoformat(dt)

    text = f"{dt.strftime('%d.%m.%Y %H:%M')}\n{desc}"

    if image:
        await call.message.answer_photo(image, caption=text)
    else:
        await call.message.answer(text)

# ===== SET IMAGE =====
@dp.message(F.photo)
async def admin_set_image(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    state = message.caption
    if not state or not state.startswith("IMAGE_FOR:"):
        return

    cid = int(state.split(":")[1])
    file_id = message.photo[-1].file_id

    cur.execute(
        "UPDATE concerts SET image_file_id=? WHERE id=?",
        (file_id, cid)
    )
    db.commit()

    await message.answer("Картинка обновлена.")

# ===== SUBSCRIBE =====
@dp.callback_query(F.data.startswith("sub:"))
async def subscribe(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (call.from_user.id, cid, datetime.now(MOSCOW_TZ).isoformat())
    )
    db.commit()
    await call.answer("Напоминание включено", show_alert=True)

@dp.callback_query(F.data.startswith("unsub:"))
async def unsubscribe(call: CallbackQuery):
    cid = int(call.data.split(":")[1])
    cur.execute(
        "DELETE FROM subscriptions WHERE user_id=? AND concert_id=?",
        (call.from_user.id, cid)
    )
    db.commit()
    await call.answer("Вы отписались", show_alert=True)

# ===== START =====
async def main():
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

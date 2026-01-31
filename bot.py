import asyncio
import sqlite3
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import Command

from apscheduler.schedulers.asyncio import AsyncIOScheduler

# === НАСТРОЙКИ КОНЦЕРТА ===
CONCERT_DATETIME = datetime(2026, 2, 13, 19, 30)  # ГОД, МЕСЯЦ, ДЕНЬ, ЧАС, МИНУТА
CONCERT_DESCRIPTION = "Концерт «Краснову 50» на Курочина 5. Начало в 19:30."

TOKEN = "ТВОЙ_TOKEN"
ADMIN_ID = 123456789
# ==========================

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler()

db = sqlite3.connect("users.db")
cur = db.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")
db.commit()


def reminder_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(
                text="Напомнить о концерте",
                callback_data="subscribe"
            )]
        ]
    )


@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Нажмите кнопку, чтобы получить напоминание о концерте.",
        reply_markup=reminder_keyboard()
    )


@dp.callback_query(F.data == "subscribe")
async def subscribe(callback: CallbackQuery):
    user_id = callback.from_user.id

    cur.execute(
        "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
        (user_id,)
    )
    db.commit()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    await callback.answer("Готово! Я напомню о концерте.")

    await callback.message.edit_text(
        "Вы подписаны на напоминание о концерте."
    )

    await bot.send_message(
        ADMIN_ID,
        f"+1 человек подписался. Всего: {count}"
    )


@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    await message.answer(f"Всего подписались: {count}")


async def send_message_to_all(text: str):
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    for (user_id,) in users:
        try:
            await bot.send_message(user_id, text)
        except:
            pass


async def reminder_morning():
    text = (
        "Сегодня концерт.\n\n"
        f"{CONCERT_DESCRIPTION}"
    )
    await send_message_to_all(text)


async def reminder_before():
    text = (
        "До концерта осталось 1,5 часа.\n\n"
        f"{CONCERT_DESCRIPTION}"
    )
    await send_message_to_all(text)


async def main():
    scheduler.add_job(
        reminder_morning,
        trigger="date",
        run_date=CONCERT_DATETIME.replace(hour=11, minute=0)
    )

    scheduler.add_job(
        reminder_before,
        trigger="date",
        run_date=CONCERT_DATETIME - timedelta(hours=1, minutes=30)
    )

    scheduler.start()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

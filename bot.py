import asyncio
import sqlite3
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.filters import Command

TOKEN = "8566906143:AAEnKS_c7-oa7DxOr4fOra36CSooWn674GE"
ADMIN_ID = 534395347  # твой telegram user_id
CONCERT_TEXT = "Сегодня концерт. Ждём тебя."

bot = Bot(token=TOKEN)
dp = Dispatcher()

db = sqlite3.connect("users.db")
cur = db.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY
)
""")
db.commit()

@dp.message(Command("start"))
async def start(message: Message):
    user_id = message.from_user.id
    cur.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    db.commit()

    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]

    await message.answer(
        "Готово. Я напомню тебе в день концерта."
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

async def send_concert_reminder():
    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    for (user_id,) in users:
        try:
            await bot.send_message(user_id, CONCERT_TEXT)
        except:
            pass

async def main():
    asyncio.create_task(dp.start_polling(bot))

    # РАСКОММЕНТИРОВАТЬ В ДЕНЬ КОНЦЕРТА
    # await send_concert_reminder()

    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())

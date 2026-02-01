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
    InputMediaPhoto,
)
from aiogram.filters import Command
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import logging
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound

# ===== НАСТРОЙКИ =====
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
MOSCOW_TZ = ZoneInfo("Europe/Moscow")
REMINDER_OFFSET_MINUTES = 2
# ====================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=MOSCOW_TZ)

# ===== FSM (ожидание картинки концерта) =====
PENDING_IMAGE = {}

# ===== БАЗА =====
db = sqlite3.connect("concerts.db", check_same_thread=False)
cur = db.cursor()

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS concerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        datetime TEXT,
        description TEXT,
        image_file_id TEXT
    )
    """
)

cur.execute(
    """
    CREATE TABLE IF NOT EXISTS subscriptions (
        user_id INTEGER,
        concert_id INTEGER,
        subscribed_at TEXT,
        PRIMARY KEY (user_id, concert_id)
    )
    """
)

db.commit()

# ===== КНОПКИ =====
def select_concert_keyboard(concert_id: int, title: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=title, callback_data=f"concert:{concert_id}")]
        ]
    )


def concert_keyboard(concert_id: int, user_id: int):
    cur.execute(
        "SELECT 1 FROM subscriptions WHERE user_id = ? AND concert_id = ?",
        (user_id, concert_id),
    )
    is_subscribed = cur.fetchone() is not None

    cur.execute(
        "SELECT COUNT(*) FROM subscriptions WHERE concert_id = ?",
        (concert_id,),
    )
    count = cur.fetchone()[0]

    buttons = []

    if is_subscribed:
        buttons.append(
            InlineKeyboardButton(text="Напоминание включено", callback_data="noop")
        )
        buttons.append(
            InlineKeyboardButton(
                text="Отписаться", callback_data=f"unsub:{concert_id}"
            )
        )
    else:
        buttons.append(
            InlineKeyboardButton(
                text=f"Напомнить ({count})", callback_data=f"sub:{concert_id}"
            )
        )

    return InlineKeyboardMarkup(inline_keyboard=[buttons])


# ===== ВСПОМОГАТЕЛЬНО =====
def now_moscow():
    return datetime.now(MOSCOW_TZ)


def parse_dt(date_str, time_str):
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(
        tzinfo=MOSCOW_TZ
    )


def schedule_concert_reminder(concert_id: int, concert_dt: datetime):
    reminder_time = concert_dt - timedelta(minutes=REMINDER_OFFSET_MINUTES)
    if reminder_time <= now_moscow():
        return

    scheduler.add_job(
        send_reminder,
        trigger="date",
        run_date=reminder_time,
        args=[concert_id],
        id=f"concert_{concert_id}",
        replace_existing=True,
    )


def restore_scheduler_from_db():
    cur.execute(
        "SELECT id, datetime FROM concerts WHERE datetime > ?",
        (now_moscow().isoformat(),),
    )
    for concert_id, dt_str in cur.fetchall():
        try:
            dt = datetime.fromisoformat(dt_str)
        except ValueError:
            continue
        schedule_concert_reminder(concert_id, dt)


async def send_reminder(concert_id: int):
    cur.execute(
        "SELECT image_file_id, description, datetime FROM concerts WHERE id = ?",
        (concert_id,),
    )
    row = cur.fetchone()
    if not row:
        return

    image_id, description, dt_str = row
    dt = datetime.fromisoformat(dt_str)

    text = (
        "Скоро концерт!\n\n"
        f"{description}\n"
        f"📅 {dt.strftime('%d.%m.%Y %H:%M')}"
    )

    cur.execute(
        "SELECT user_id FROM subscriptions WHERE concert_id = ?",
        (concert_id,),
    )

    for (user_id,) in cur.fetchall():
        try:
            if image_id:
                await bot.send_photo(user_id, photo=image_id, caption=text)
            else:
                await bot.send_message(user_id, text)
        except (TelegramForbiddenError, TelegramNotFound):
            cur.execute(
                "DELETE FROM subscriptions WHERE user_id = ? AND concert_id = ?",
                (user_id, concert_id),
            )
            db.commit()
            logging.warning(
                f"User {user_id} removed from subscriptions for concert {concert_id}"
            )
        except Exception as e:
            logging.exception(f"Failed to send reminder to user {user_id}: {e}")


# ===== /start =====
@dp.message(Command("start"))
async def start(message: Message):
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Показать концерты", callback_data="show_concerts")]
        ]
    )

    await message.answer(
        "Привет. Я напомню о предстоящих концертах.\n\n"
        "Нажми кнопку ниже, чтобы посмотреть афишу и включить напоминание.",
        reply_markup=keyboard,
    )


# ===== CALLBACK: ПОКАЗАТЬ КОНЦЕРТЫ =====

@dp.callback_query(F.data == "show_concerts")
async def show_concerts(call: CallbackQuery):
    cur.execute(
        "SELECT id, description FROM concerts WHERE datetime > ? ORDER BY datetime",
        (now_moscow().isoformat(),),
    )
    concerts = cur.fetchall()

    if not concerts:
        await call.message.edit_text("Пока нет запланированных концертов.")
        await call.answer()
        return

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=desc, callback_data=f"concert:{cid}")]
            for cid, desc in concerts
        ]
    )

    await call.message.edit_text("Выбери концерт:", reply_markup=keyboard)
    await call.answer()


# ===== /setconcert (admin) =====
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
        (dt.isoformat(), description),
    )
    concert_id = cur.lastrowid
    db.commit()

    schedule_concert_reminder(concert_id, dt)
    PENDING_IMAGE[message.from_user.id] = concert_id

    await message.answer(
        "Концерт добавлен.\n\nТеперь пришли картинку ответом на это сообщение."
    )


# ===== СОХРАНЕНИЕ КАРТИНКИ =====
@dp.message(F.photo)
async def save_image(message: Message):
    if message.from_user.id != ADMIN_ID:
        return

    concert_id = PENDING_IMAGE.get(message.from_user.id)
    if not concert_id:
        await message.answer("Нет активного концерта для привязки картинки.")
        return

    photo = message.photo[-1]

    cur.execute(
        "UPDATE concerts SET image_file_id = ? WHERE id = ?",
        (photo.file_id, concert_id),
    )
    db.commit()

    PENDING_IMAGE.pop(message.from_user.id, None)
    await message.answer("Картинка сохранена для концерта.")


# ===== CALLBACK: ВЫБОР КОНЦЕРТА =====
@dp.callback_query(F.data.startswith("concert:"))
async def show_concert(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        """
        SELECT datetime, description, image_file_id
        FROM concerts
        WHERE id = ? AND datetime > ?
        """,
        (concert_id, now_moscow().isoformat()),
    )
    row = cur.fetchone()

    if not row:
        await call.answer("Концерт не найден", show_alert=True)
        return

    dt_str, desc, image_id = row
    dt = datetime.fromisoformat(dt_str)

    text = f"{desc}\n\n📅 {dt.strftime('%d.%m.%Y %H:%M')}"

    if image_id:
        await call.message.edit_media(
            InputMediaPhoto(media=image_id, caption=text),
            reply_markup=concert_keyboard(concert_id, call.from_user.id),
        )
    else:
        await call.message.edit_text(
            text, reply_markup=concert_keyboard(concert_id, call.from_user.id)
        )

    await call.answer()


# ===== CALLBACK: ПОДПИСКА =====
@dp.callback_query(F.data.startswith("sub:"))
async def subscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "INSERT OR IGNORE INTO subscriptions VALUES (?, ?, ?)",
        (call.from_user.id, concert_id, now_moscow().isoformat()),
    )
    db.commit()

    await call.message.edit_reply_markup(
        reply_markup=concert_keyboard(concert_id, call.from_user.id)
    )
    await call.answer("Напоминание включено")


# ===== CALLBACK: NOOP =====
@dp.callback_query(F.data == "noop")
async def noop_handler(call: CallbackQuery):
    await call.answer("Уже включено")


# ===== CALLBACK: ОТПИСКА =====
@dp.callback_query(F.data.startswith("unsub:"))
async def unsubscribe(call: CallbackQuery):
    concert_id = int(call.data.split(":")[1])

    cur.execute(
        "DELETE FROM subscriptions WHERE user_id = ? AND concert_id = ?",
        (call.from_user.id, concert_id),
    )
    db.commit()

    await call.message.edit_reply_markup(
        reply_markup=concert_keyboard(concert_id, call.from_user.id)
    )
    await call.answer("Вы отписались")


# ===== ЗАПУСК =====
async def main():
    scheduler.start()
    restore_scheduler_from_db()
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

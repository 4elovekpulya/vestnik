import asyncio
import logging
from datetime import datetime

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from config import load_config
from db import Database
from handlers import build_router
from scheduler import ReminderScheduler


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


async def main() -> None:
    config = load_config()
    bot = Bot(token=config.token)
    storage = MemoryStorage()
    dispatcher = Dispatcher(storage=storage)
    db = Database(config.db_path)
    scheduler = ReminderScheduler(db, bot, config.timezone)
    router = build_router(config, db, scheduler)
    dispatcher.include_router(router)
    scheduler.start()
    scheduler.restore(now=datetime.now(config.timezone))
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

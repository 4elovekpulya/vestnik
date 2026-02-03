from __future__ import annotations

from datetime import datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNotFound
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from db import Database


class ReminderScheduler:
    def __init__(self, db: Database, bot: Bot, timezone):
        self._db = db
        self._bot = bot
        self._scheduler = AsyncIOScheduler(timezone=timezone)

    def start(self) -> None:
        self._scheduler.start()

    def shutdown(self) -> None:
        self._scheduler.shutdown()

    def restore(self, now: datetime) -> None:
        for event in self._db.list_future_events(now):
            self.schedule_event(event.id, event.start_at, event.reminder_minutes)

    def schedule_event(self, event_id: int, start_at: datetime, reminder_minutes: int) -> None:
        reminder_time = start_at - timedelta(minutes=reminder_minutes)
        if reminder_time <= datetime.now(start_at.tzinfo):
            return
        self._scheduler.add_job(
            self.send_reminder,
            trigger="date",
            run_date=reminder_time,
            args=[event_id],
            id=f"event_{event_id}",
            replace_existing=True,
        )

    def remove_event(self, event_id: int) -> None:
        job_id = f"event_{event_id}"
        if self._scheduler.get_job(job_id):
            self._scheduler.remove_job(job_id)

    async def send_reminder(self, event_id: int) -> None:
        event = self._db.get_event(event_id)
        if not event:
            return
        text = (
            "Скоро событие!\n\n"
            f"{event.text}\n"
            f"📅 {event.start_at.strftime('%d.%m.%Y %H:%M')}"
        )
        subscribers = self._db.list_subscribers(event_id)
        for user_id in subscribers:
            try:
                if event.image_file_id:
                    await self._bot.send_photo(user_id, photo=event.image_file_id, caption=text)
                else:
                    await self._bot.send_message(user_id, text)
            except (TelegramForbiddenError, TelegramNotFound):
                self._db.remove_subscription(user_id, event_id)

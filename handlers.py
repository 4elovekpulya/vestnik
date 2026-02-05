from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from config import Config
from db import Database, Event
from keyboards import (
    admin_confirm_delete_keyboard,
    admin_image_skip_keyboard,
    admin_manage_keyboard,
    event_keyboard,
    event_list_item_keyboard,
    main_menu_keyboard,
)
from scheduler import ReminderScheduler
from states import AdminCreateEvent, AdminEditEvent


def build_router(config: Config, db: Database, scheduler: ReminderScheduler) -> Router:
    router = Router()

    def is_admin(user_id: int) -> bool:
        return user_id in config.admin_ids

    def now_moscow() -> datetime:
        return datetime.now(config.timezone)

    def event_title(event: Event) -> str:
        return f"{event.text}\n📅 {event.start_at.strftime('%d.%m.%Y %H:%M')}"

    async def show_event(message: Message | CallbackQuery, event_id: int, user_id: int) -> None:
        event = db.get_event(event_id)
        if not event or event.start_at <= now_moscow():
            await _answer(message, "Событие не найдено или уже прошло.")
            return
        subscribers_count = db.count_subscriptions(event_id)
        is_subscribed = db.is_subscribed(user_id, event_id)
        text = (
            f"{event.text}\n\n"
            f"📅 {event.start_at.strftime('%d.%m.%Y %H:%M')}\n"
            f"👥 Подписчиков: {subscribers_count}"
        )
        keyboard = event_keyboard(is_subscribed, subscribers_count, is_admin(user_id), event_id)
        await _answer(message, text, image_id=event.image_file_id, keyboard=keyboard)

    async def _answer(
        target: Message | CallbackQuery,
        text: str,
        image_id: str | None = None,
        keyboard=None,
    ) -> None:
        if isinstance(target, CallbackQuery):
            message = target.message
        else:
            message = target
        if image_id:
            await message.answer_photo(photo=image_id, caption=text, reply_markup=keyboard)
        else:
            await message.answer(text, reply_markup=keyboard)

    @router.message(CommandStart())
    async def start(message: Message, state: FSMContext) -> None:
        await state.clear()
        parts = message.text.split(maxsplit=1)
        if len(parts) == 2 and parts[1].startswith("event_"):
            try:
                event_id = int(parts[1].replace("event_", ""))
            except ValueError:
                await message.answer("Событие не найдено.")
                return
            await show_event(message, event_id, message.from_user.id)
            return
        user_id = message.from_user.id
        admin_flag = is_admin(user_id)
        await message.answer(
            "Привет! Я помогу не пропустить события.",
            reply_markup=main_menu_keyboard(is_admin=admin_flag),
        )

    @router.callback_query(F.data == "menu")
    async def open_menu(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        await call.message.answer(
            "Главное меню:",
            reply_markup=main_menu_keyboard(is_admin(call.from_user.id)),
        )
        await call.answer()

    @router.callback_query(F.data == "events:list")
    async def list_events(call: CallbackQuery) -> None:
        events = db.list_future_events(now_moscow())
        if not events:
            await call.message.answer("Пока нет будущих событий.")
            await call.answer()
            return
        for event in events:
            await _answer(
                call,
                event_title(event),
                image_id=event.image_file_id,
                keyboard=event_list_item_keyboard(event.id),
            )
        await call.answer()

    @router.callback_query(F.data.startswith("event:open:"))
    async def open_event(call: CallbackQuery) -> None:
        event_id = int(call.data.split(":")[-1])
        await show_event(call, event_id, call.from_user.id)
        await call.answer()

    @router.callback_query(F.data.startswith("event:sub:"))
    async def subscribe(call: CallbackQuery) -> None:
        event_id = int(call.data.split(":")[-1])
        event = db.get_event(event_id)
        if not event or event.start_at <= now_moscow():
            await call.answer("Событие недоступно", show_alert=True)
            return
        db.add_subscription(call.from_user.id, event_id, now_moscow())
        await show_event(call, event_id, call.from_user.id)
        await call.answer("Напоминание включено")

    @router.callback_query(F.data.startswith("event:unsub:"))
    async def unsubscribe(call: CallbackQuery) -> None:
        event_id = int(call.data.split(":")[-1])
        db.remove_subscription(call.from_user.id, event_id)
        await show_event(call, event_id, call.from_user.id)
        await call.answer("Вы отписались")

    @router.callback_query(F.data == "noop")
    async def noop(call: CallbackQuery) -> None:
        await call.answer("Уже включено")

    @router.callback_query(F.data == "admin:create")
    async def admin_create(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        await state.set_state(AdminCreateEvent.waiting_datetime)
        await call.message.answer("Введите дату и время события в формате: YYYY-MM-DD HH:MM")
        await call.answer()

    @router.message(AdminCreateEvent.waiting_datetime)
    async def admin_create_datetime(message: Message, state: FSMContext) -> None:
        try:
            start_at = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer("Неверный формат. Пример: 2024-12-31 19:30")
            return
        start_at = start_at.replace(tzinfo=config.timezone)
        await state.update_data(start_at=start_at)
        await state.set_state(AdminCreateEvent.waiting_text)
        await message.answer("Введите текст анонса.")

    @router.message(AdminCreateEvent.waiting_text)
    async def admin_create_text(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        if not text:
            await message.answer("Текст не должен быть пустым.")
            return
        await state.update_data(text=text)
        await state.set_state(AdminCreateEvent.waiting_reminder)
        await message.answer("За сколько минут напомнить? Введите число.")

    @router.message(AdminCreateEvent.waiting_reminder)
    async def admin_create_reminder(message: Message, state: FSMContext) -> None:
        try:
            minutes = int(message.text.strip())
        except ValueError:
            await message.answer("Введите целое число.")
            return
        if minutes <= 0:
            await message.answer("Значение должно быть больше нуля.")
            return
        data = await state.get_data()
        event_id = db.create_event(
            start_at=data["start_at"],
            text=data["text"],
            reminder_minutes=minutes,
        )
        scheduler.schedule_event(event_id, data["start_at"], minutes)
        await state.update_data(event_id=event_id)
        await state.set_state(AdminCreateEvent.waiting_image)
        await message.answer(
            "Событие создано! Пришлите изображение или нажмите «Пропустить».",
            reply_markup=admin_image_skip_keyboard(event_id),
        )
        await message.answer(
            f"Ссылка на событие: t.me/{(await message.bot.get_me()).username}?start=event_{event_id}"
        )

    @router.message(AdminCreateEvent.waiting_image, F.photo)
    async def admin_create_image(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        event_id = data["event_id"]
        photo = message.photo[-1]
        db.update_event(event_id, image_file_id=photo.file_id)
        await state.clear()
        await message.answer("Изображение сохранено.")
        await show_event(message, event_id, message.from_user.id)

    @router.callback_query(AdminCreateEvent.waiting_image, F.data.startswith("admin:image_skip:"))
    async def admin_create_image_skip(call: CallbackQuery, state: FSMContext) -> None:
        await state.clear()
        event_id = int(call.data.split(":")[-1])
        await call.message.answer("Изображение пропущено.")
        await show_event(call, event_id, call.from_user.id)
        await call.answer()

    @router.callback_query(F.data.startswith("admin:manage:"))
    async def admin_manage(call: CallbackQuery) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await call.message.answer(
            "Управление событием:",
            reply_markup=admin_manage_keyboard(event_id),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("admin:delete:"))
    async def admin_delete(call: CallbackQuery) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await call.message.answer(
            "Удалить событие?",
            reply_markup=admin_confirm_delete_keyboard(event_id),
        )
        await call.answer()

    @router.callback_query(F.data.startswith("admin:confirm_delete:"))
    async def admin_confirm_delete(call: CallbackQuery) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        db.delete_event(event_id)
        scheduler.remove_event(event_id)
        await call.message.answer("Событие удалено.")
        await call.answer()

    @router.callback_query(F.data.startswith("admin:edit_dt:"))
    async def admin_edit_dt(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await state.update_data(event_id=event_id)
        await state.set_state(AdminEditEvent.waiting_datetime)
        await call.message.answer("Введите новую дату и время: YYYY-MM-DD HH:MM")
        await call.answer()

    @router.message(AdminEditEvent.waiting_datetime)
    async def admin_edit_dt_message(message: Message, state: FSMContext) -> None:
        try:
            start_at = datetime.strptime(message.text.strip(), "%Y-%m-%d %H:%M")
        except ValueError:
            await message.answer("Неверный формат даты.")
            return
        start_at = start_at.replace(tzinfo=config.timezone)
        data = await state.get_data()
        event_id = data["event_id"]
        event = db.get_event(event_id)
        if not event:
            await message.answer("Событие не найдено.")
            await state.clear()
            return
        db.update_event(event_id, start_at=start_at)
        scheduler.schedule_event(event_id, start_at, event.reminder_minutes)
        await state.clear()
        await message.answer("Дата обновлена.")
        await show_event(message, event_id, message.from_user.id)

    @router.callback_query(F.data.startswith("admin:edit_text:"))
    async def admin_edit_text(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await state.update_data(event_id=event_id)
        await state.set_state(AdminEditEvent.waiting_text)
        await call.message.answer("Введите новый текст анонса.")
        await call.answer()

    @router.message(AdminEditEvent.waiting_text)
    async def admin_edit_text_message(message: Message, state: FSMContext) -> None:
        text = message.text.strip()
        if not text:
            await message.answer("Текст не должен быть пустым.")
            return
        data = await state.get_data()
        event_id = data["event_id"]
        db.update_event(event_id, text=text)
        await state.clear()
        await message.answer("Текст обновлён.")
        await show_event(message, event_id, message.from_user.id)

    @router.callback_query(F.data.startswith("admin:edit_reminder:"))
    async def admin_edit_reminder(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await state.update_data(event_id=event_id)
        await state.set_state(AdminEditEvent.waiting_reminder)
        await call.message.answer("Введите новое значение напоминания (минуты).")
        await call.answer()

    @router.message(AdminEditEvent.waiting_reminder)
    async def admin_edit_reminder_message(message: Message, state: FSMContext) -> None:
        try:
            minutes = int(message.text.strip())
        except ValueError:
            await message.answer("Введите целое число.")
            return
        if minutes <= 0:
            await message.answer("Значение должно быть больше нуля.")
            return
        data = await state.get_data()
        event_id = data["event_id"]
        event = db.get_event(event_id)
        if not event:
            await message.answer("Событие не найдено.")
            await state.clear()
            return
        db.update_event(event_id, reminder_minutes=minutes)
        scheduler.schedule_event(event_id, event.start_at, minutes)
        await state.clear()
        await message.answer("Напоминание обновлено.")
        await show_event(message, event_id, message.from_user.id)

    @router.callback_query(F.data.startswith("admin:edit_image:"))
    async def admin_edit_image(call: CallbackQuery, state: FSMContext) -> None:
        if not is_admin(call.from_user.id):
            await call.answer()
            return
        event_id = int(call.data.split(":")[-1])
        await state.update_data(event_id=event_id)
        await state.set_state(AdminEditEvent.waiting_image)
        await call.message.answer("Пришлите новое изображение.")
        await call.answer()

    @router.message(AdminEditEvent.waiting_image, F.photo)
    async def admin_edit_image_message(message: Message, state: FSMContext) -> None:
        data = await state.get_data()
        event_id = data["event_id"]
        photo = message.photo[-1]
        db.update_event(event_id, image_file_id=photo.file_id)
        await state.clear()
        await message.answer("Изображение обновлено.")
        await show_event(message, event_id, message.from_user.id)

    return router

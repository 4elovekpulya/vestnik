from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu_keyboard(is_admin: bool) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Все события", callback_data="events:list")]]
    if is_admin:
        rows.append([InlineKeyboardButton(text="➕ Создать событие", callback_data="admin:create")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_keyboard(is_subscribed: bool, subscribers_count: int, is_admin: bool, event_id: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if is_subscribed:
        rows.append([InlineKeyboardButton(text="🔔 Напоминание включено", callback_data="noop")])
        rows.append([InlineKeyboardButton(text="Отписаться", callback_data=f"event:unsub:{event_id}")])
    else:
        rows.append([
            InlineKeyboardButton(
                text=f"🔔 Напомнить ({subscribers_count})",
                callback_data=f"event:sub:{event_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="Все события", callback_data="events:list")])
    if is_admin:
        rows.append([InlineKeyboardButton(text="⚙️ Управление", callback_data=f"admin:manage:{event_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def event_list_item_keyboard(event_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Открыть", callback_data=f"event:open:{event_id}")],
        [InlineKeyboardButton(text="В меню", callback_data="menu")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_manage_keyboard(event_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="✏️ Редактировать дату", callback_data=f"admin:edit_dt:{event_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать текст", callback_data=f"admin:edit_text:{event_id}")],
        [InlineKeyboardButton(text="✏️ Редактировать напоминание", callback_data=f"admin:edit_reminder:{event_id}")],
        [InlineKeyboardButton(text="🖼 Заменить изображение", callback_data=f"admin:edit_image:{event_id}")],
        [InlineKeyboardButton(text="🗑 Удалить событие", callback_data=f"admin:delete:{event_id}")],
        [InlineKeyboardButton(text="Назад", callback_data=f"event:open:{event_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_confirm_delete_keyboard(event_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Удалить", callback_data=f"admin:confirm_delete:{event_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"admin:manage:{event_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_image_skip_keyboard(event_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Пропустить", callback_data=f"admin:image_skip:{event_id}")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

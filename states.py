from aiogram.fsm.state import State, StatesGroup


class AdminCreateEvent(StatesGroup):
    waiting_datetime = State()
    waiting_text = State()
    waiting_reminder = State()
    waiting_image = State()


class AdminEditEvent(StatesGroup):
    waiting_datetime = State()
    waiting_text = State()
    waiting_reminder = State()
    waiting_image = State()

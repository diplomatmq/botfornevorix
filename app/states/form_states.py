from aiogram.fsm.state import State, StatesGroup


class CreateRefLinkState(StatesGroup):
    confirm = State()


class CreateLotState(StatesGroup):
    choosing_refs = State()
    count = State()
    price = State()
    confirm = State()


class CreateGiveawayState(StatesGroup):
    title = State()
    prize = State()
    text = State()
    ends_at = State()
    winners_count = State()
    prizes = State()
    min_level = State()
    confirm = State()


class GiveawayActionState(StatesGroup):
    cancel_id = State()
    finish_id = State()


class DepositRequestState(StatesGroup):
    amount = State()
    screenshot = State()


class WithdrawRequestState(StatesGroup):
    amount = State()
    details = State()


class AdminSetLevelState(StatesGroup):
    user_identifier = State()
    level = State()
    confirm = State()


class RequestRejectState(StatesGroup):
    comment = State()


class AdminRequestCheckState(StatesGroup):
    """Состояние для проверки заявки по номеру"""
    request_id = State()


class BroadcastState(StatesGroup):
    text = State()
    confirm = State()

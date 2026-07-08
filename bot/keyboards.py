from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from exchanges.base import BaseExchange


class MenuCb(CallbackData, prefix="m"):
    action: str          # main | exch | rubric | t_notify | t_rubric | t_attr | close
    exchange: str = ""
    rubric: str = ""
    attr: str = ""


def _mark(enabled: bool) -> str:
    return "✅" if enabled else "🔕"


def order_kb() -> InlineKeyboardMarkup:
    """Клавиатура под уведомлением о заказе."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🗑 Удалить",
                             callback_data=MenuCb(action="del_order").pack()),
    ]])


def main_menu(notify_enabled: bool, exchanges: list[BaseExchange]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text=f"🔔 Уведомления: {'ВКЛ' if notify_enabled else 'ВЫКЛ'}",
        callback_data=MenuCb(action="t_notify").pack(),
    ))
    for exchange in exchanges:
        kb.row(InlineKeyboardButton(
            text=f"📁 {exchange.title}",
            callback_data=MenuCb(action="exch", exchange=exchange.name).pack(),
        ))
    kb.row(InlineKeyboardButton(text="✖️ Закрыть",
                                callback_data=MenuCb(action="close").pack()))
    return kb.as_markup()


def exchange_menu(exchange: BaseExchange,
                  states: dict[tuple[str, str], bool]) -> InlineKeyboardMarkup:
    """Список рубрик биржи: тумблер + кнопка подрубрик."""
    kb = InlineKeyboardBuilder()
    for rubric in exchange.rubrics():
        enabled = states.get((rubric.id, ""), False)
        kb.row(
            InlineKeyboardButton(
                text=f"{_mark(enabled)} {rubric.title}",
                callback_data=MenuCb(action="t_rubric", exchange=exchange.name,
                                     rubric=rubric.id).pack(),
            ),
            InlineKeyboardButton(
                text="⚙️",
                callback_data=MenuCb(action="rubric", exchange=exchange.name,
                                     rubric=rubric.id).pack(),
            ),
        )
    kb.row(InlineKeyboardButton(text="⬅️ Назад",
                                callback_data=MenuCb(action="main").pack()))
    return kb.as_markup()


def rubric_menu(exchange: BaseExchange, rubric_id: str,
                states: dict[tuple[str, str], bool]) -> InlineKeyboardMarkup:
    rubric = next(r for r in exchange.rubrics() if r.id == rubric_id)
    kb = InlineKeyboardBuilder()
    for sub in rubric.subrubrics:
        enabled = states.get((rubric.id, sub.id), False)
        kb.row(InlineKeyboardButton(
            text=f"{_mark(enabled)} {sub.title}",
            callback_data=MenuCb(action="t_attr", exchange=exchange.name,
                                 rubric=rubric.id, attr=sub.id).pack(),
        ))
    kb.row(InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data=MenuCb(action="exch", exchange=exchange.name).pack(),
    ))
    return kb.as_markup()

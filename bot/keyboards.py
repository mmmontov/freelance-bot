from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from exchanges.base import BaseExchange


class MenuCb(CallbackData, prefix="m"):
    action: str          # main | exch | rubric | t_notify | t_silent | t_rubric | t_attr | draft | redraft | close
    exchange: str = ""
    rubric: str = ""
    attr: str = ""
    order_id: str = ""


def _mark(enabled: bool) -> str:
    return "✅" if enabled else "🔕"


def order_kb(exchange: str, order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура под уведомлением о заказе."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="✍️ Черновик отклика",
            callback_data=MenuCb(action="draft", exchange=exchange,
                                 order_id=order_id).pack(),
        ),
        InlineKeyboardButton(text="🗑 Удалить",
                             callback_data=MenuCb(action="del_order").pack()),
    ]])


def draft_kb(exchange: str, order_id: str) -> InlineKeyboardMarkup:
    """Клавиатура под сообщением с черновиком отклика."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="🔄 Перегенерировать",
            callback_data=MenuCb(action="redraft", exchange=exchange,
                                 order_id=order_id).pack(),
        ),
    ]])


def main_menu(notify_enabled: bool, silent: bool,
             exchanges: list[BaseExchange]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.row(InlineKeyboardButton(
        text=f"🔔 Уведомления: {'ВКЛ' if notify_enabled else 'ВЫКЛ'}",
        callback_data=MenuCb(action="t_notify").pack(),
    ))
    kb.row(InlineKeyboardButton(
        text=f"{'🔇 Без звука' if silent else '🔊 Со звуком'}",
        callback_data=MenuCb(action="t_silent").pack(),
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

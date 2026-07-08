from aiogram import Router
from aiogram.types import CallbackQuery

from bot.keyboards import MenuCb, exchange_menu, main_menu, rubric_menu
from exchanges.registry import EXCHANGES
from storage.repository import ChatRepo, SubscriptionRepo

router = Router()


@router.callback_query(MenuCb.filter())
async def on_menu(callback: CallbackQuery, callback_data: MenuCb,
                  chat_repo: ChatRepo, sub_repo: SubscriptionRepo) -> None:
    chat_id = callback.message.chat.id
    action = callback_data.action

    if action in ("close", "del_order"):
        await callback.message.delete()
        await callback.answer()
        return

    if action == "t_notify":
        enabled = await chat_repo.toggle(chat_id)
        await callback.answer(
            "Уведомления включены" if enabled else "Уведомления выключены"
        )
        action = "main"
    elif action == "t_silent":
        silent = await chat_repo.toggle_silent(chat_id)
        await callback.answer(
            "Уведомления без звука" if silent else "Уведомления со звуком"
        )
        action = "main"
    elif action == "t_rubric":
        await sub_repo.toggle(chat_id, callback_data.exchange, callback_data.rubric)
        await callback.answer()
        action = "exch"
    elif action == "t_attr":
        await sub_repo.toggle(chat_id, callback_data.exchange,
                              callback_data.rubric, callback_data.attr)
        await callback.answer()
        action = "rubric"
    else:
        await callback.answer()

    if action == "main":
        notify = await chat_repo.is_enabled(chat_id)
        silent = await chat_repo.is_silent(chat_id)
        markup = main_menu(notify, silent, list(EXCHANGES.values()))
    else:
        exchange = EXCHANGES[callback_data.exchange]
        states = await sub_repo.get_states(chat_id, exchange.name)
        if action == "exch":
            markup = exchange_menu(exchange, states)
        else:  # rubric
            markup = rubric_menu(exchange, callback_data.rubric, states)

    if callback.message.reply_markup != markup:
        await callback.message.edit_reply_markup(reply_markup=markup)

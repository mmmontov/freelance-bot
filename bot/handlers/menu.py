import html
import logging

from aiogram import Router
from aiogram.enums import ChatAction
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from groq import AsyncGroq

from bot.draftgen import generate_draft
from bot.keyboards import MenuCb, draft_kb, exchange_menu, main_menu, rubric_menu
from exchanges.registry import EXCHANGES
from storage.repository import ChatRepo, OrderCacheRepo, SubscriptionRepo

logger = logging.getLogger(__name__)

router = Router()


@router.callback_query(MenuCb.filter())
async def on_menu(callback: CallbackQuery, callback_data: MenuCb,
                  chat_repo: ChatRepo, sub_repo: SubscriptionRepo,
                  order_cache: OrderCacheRepo, groq_client: AsyncGroq | None) -> None:
    chat_id = callback.message.chat.id
    action = callback_data.action

    if action in ("close", "del_order"):
        await callback.message.delete()
        await callback.answer()
        return

    if action in ("draft", "redraft"):
        await _send_draft(callback, callback_data, order_cache, groq_client,
                          edit=(action == "redraft"))
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


async def _send_draft(callback: CallbackQuery, callback_data: MenuCb,
                      order_cache: OrderCacheRepo, groq_client: AsyncGroq | None,
                      edit: bool = False) -> None:
    if groq_client is None:
        await callback.answer(
            "Черновики не настроены (нет GROQ_API_KEY)", show_alert=True
        )
        return

    order = await order_cache.get(callback_data.exchange, callback_data.order_id)
    if order is None:
        await callback.answer(
            "Черновик недоступен — данные о заказе устарели", show_alert=True
        )
        return

    await callback.answer("Генерирую новый вариант…" if edit else None)
    await callback.bot.send_chat_action(callback.message.chat.id, ChatAction.TYPING)
    try:
        draft = await generate_draft(groq_client, order)
    except Exception:
        logger.exception("Не удалось сгенерировать черновик для заказа %s",
                         order.order_id)
        if edit:
            await callback.answer("Не удалось сгенерировать черновик", show_alert=True)
        else:
            await callback.message.answer(
                "Не удалось сгенерировать черновик, попробуй ещё раз позже."
            )
        return

    kb = draft_kb(callback_data.exchange, callback_data.order_id)
    if edit:
        try:
            await callback.message.edit_text(html.escape(draft), reply_markup=kb)
        except TelegramBadRequest:
            # текст черновика совпал с предыдущим — Telegram не даёт "изменить"
            # сообщение на идентичный текст, это не ошибка
            pass
    else:
        await callback.message.answer(
            html.escape(draft), reply_markup=kb,
            reply_to_message_id=callback.message.message_id,
        )

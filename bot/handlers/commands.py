from aiogram import Router
from aiogram.filters import Command, ChatMemberUpdatedFilter, IS_NOT_MEMBER, IS_MEMBER
from aiogram.types import ChatMemberUpdated, Message

from bot.keyboards import main_menu
from exchanges.registry import EXCHANGES
from storage.repository import ChatRepo, SubscriptionRepo

router = Router()

WELCOME = (
    "👋 Я слежу за новыми заказами на биржах фриланса и присылаю их сюда.\n"
    "Меню настроек: /menu"
)


@router.message(Command("start"))
async def cmd_start(message: Message, chat_repo: ChatRepo) -> None:
    await chat_repo.register(message.chat.id, EXCHANGES.values())
    await message.answer(WELCOME)


@router.my_chat_member(ChatMemberUpdatedFilter(IS_NOT_MEMBER >> IS_MEMBER))
async def on_added_to_chat(event: ChatMemberUpdated, chat_repo: ChatRepo) -> None:
    await chat_repo.register(event.chat.id, EXCHANGES.values())
    await event.answer(WELCOME)


@router.message(Command("menu"))
async def cmd_menu(message: Message, chat_repo: ChatRepo) -> None:
    await chat_repo.register(message.chat.id, EXCHANGES.values())
    notify = await chat_repo.is_enabled(message.chat.id)
    silent = await chat_repo.is_silent(message.chat.id)
    await message.answer(
        "⚙️ <b>Настройки уведомлений</b>",
        reply_markup=main_menu(notify, silent, list(EXCHANGES.values())),
    )


@router.message(Command("status"))
async def cmd_status(message: Message, chat_repo: ChatRepo,
                     sub_repo: SubscriptionRepo) -> None:
    await chat_repo.register(message.chat.id, EXCHANGES.values())
    notify = await chat_repo.is_enabled(message.chat.id)
    silent = await chat_repo.is_silent(message.chat.id)
    lines = [
        f"🔔 Уведомления: {'ВКЛ' if notify else 'ВЫКЛ'}",
        f"🔊 Звук: {'ВЫКЛ' if silent else 'ВКЛ'}",
    ]
    for exchange in EXCHANGES.values():
        enabled = await sub_repo.enabled_rubrics(message.chat.id, exchange.name)
        lines.append(f"\n<b>{exchange.title}</b>")
        for rubric in exchange.rubrics():
            if rubric.id not in enabled:
                lines.append(f"🔕 {rubric.title}")
                continue
            attrs = enabled[rubric.id]
            titles = [s.title for s in rubric.subrubrics if s.id in attrs]
            if len(attrs) == len(rubric.subrubrics):
                lines.append(f"✅ {rubric.title} (все подрубрики)")
            else:
                lines.append(f"✅ {rubric.title}: {', '.join(titles)}")
    await message.answer("\n".join(lines))

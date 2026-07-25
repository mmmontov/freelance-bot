from pathlib import Path

from groq import AsyncGroq

from exchanges.base import Order

MODEL = "llama-3.3-70b-versatile"
SYSTEM_PROMPT = (
    "Ты помогаешь фрилансеру написать короткий черновик отклика на заказ "
    "с биржи Kwork. По-русски, по делу, без воды и лести, без приветствий "
    "уровня 'Здравствуйте, меня зовут...'. Строго соблюдай длину: "
    "150-200 символов, максимум 250 (считая пробелы и знаки препинания) — "
    "это жёсткое ограничение, а не пожелание. На такой длине пиши одним "
    "коротким абзацем или, если совсем нужно, двумя.\n\n"
    "Никогда не пересказывай и не повторяй своими словами условие заказа "
    "(что нужно сделать, название сайта/проекта, требования из задания) — "
    "заказчик сам это написал и уже знает. Не пиши в духе 'исправлю баг с "
    "вытянутыми фото на сайте X' или 'сделаю вам лендинг с меню и оплатой'. "
    "Вместо пересказа сразу переходи к сути: что ты умеешь/делал похожее, "
    "какой стек предлагаешь, или задай уточняющий вопрос по делу."
)

BASE_DIR = Path(__file__).resolve().parent.parent
STYLE_PROFILE_PATH = BASE_DIR / "data" / "style_profile.md"


def _load_style_profile() -> str:
    """Стек и примеры прошлых откликов пользователя — редактируется на лету
    в data/ (смонтированный volume), без пересборки контейнера."""
    try:
        return STYLE_PROFILE_PATH.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


async def generate_draft(client: AsyncGroq, order: Order) -> str:
    system = SYSTEM_PROMPT
    style = _load_style_profile()
    if style:
        system += (
            "\n\nНиже — профиль фрилансера: его стек и пронумерованные "
            "правила написания отклика, выведенные из его реальных прошлых "
            "откликов. Правила соблюдай строго и в приоритете над твоими "
            "общими соображениями. Примеры внизу — только для калибровки "
            "тона, не копируй их дословно и не переноси детали из них в "
            "новый отклик.\n\n" + style
        )

    resp = await client.chat.completions.create(
        model=MODEL,
        max_tokens=150,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": f"Заголовок: {order.title}\n\nОписание: {order.description}"},
        ],
    )
    return resp.choices[0].message.content.strip()

from pathlib import Path

from groq import AsyncGroq

from exchanges.base import Order

MODEL = "llama-3.3-70b-versatile"
SYSTEM_PROMPT = (
    "Ты помогаешь фрилансеру написать короткий черновик отклика на заказ "
    "с биржи Kwork. По-русски, по делу, без воды и лести, без приветствий "
    "уровня 'Здравствуйте, меня зовут...'. Упомяни конкретику из описания "
    "заказа, чтобы было видно, что его прочитали. Строго соблюдай длину: "
    "150-200 символов, максимум 250 (считая пробелы и знаки препинания) — "
    "это жёсткое ограничение, а не пожелание. На такой длине пиши одним "
    "коротким абзацем или, если совсем нужно, двумя."
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
            "\n\nНиже — профиль фрилансера: его стек и примеры его прошлых "
            "откликов. Ориентируйся на тон, длину и обороты речи из примеров "
            "— пиши так, будто это написал он сам.\n\n" + style
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

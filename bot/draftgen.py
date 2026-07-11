from groq import AsyncGroq

from exchanges.base import Order

MODEL = "llama-3.3-70b-versatile"
SYSTEM_PROMPT = (
    "Ты помогаешь фрилансеру написать короткий черновик отклика на заказ "
    "с биржи Kwork. 2-4 предложения, по-русски, по делу, без воды и лести, "
    "без приветствий уровня 'Здравствуйте, меня зовут...'. Упомяни конкретику "
    "из описания заказа, чтобы было видно, что его прочитали."
)


async def generate_draft(client: AsyncGroq, order: Order) -> str:
    resp = await client.chat.completions.create(
        model=MODEL,
        max_tokens=400,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Заголовок: {order.title}\n\nОписание: {order.description}"},
        ],
    )
    return resp.choices[0].message.content.strip()

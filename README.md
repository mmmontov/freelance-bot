# Freelance Bot

Telegram-бот (aiogram 3), который отслеживает новые заказы на биржах фриланса
и присылает уведомления в чат. Сейчас подключён kwork.ru.

## Запуск

```bash
cp .env.example .env   # заполнить BOT_TOKEN
venv/bin/python main.py
```

Или через systemd:

```bash
sudo cp freelance-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now freelance-bot
```

## Команды бота

- `/start` — регистрация чата (происходит и автоматически при добавлении в группу)
- `/menu` — инлайн-меню: глобальный тумблер уведомлений, вкл/выкл рубрик и подрубрик
- `/status` — текущие настройки текстом

## Архитектура

- `exchanges/base.py` — контракт биржи (`BaseExchange`, `Order`, `Rubric`).
  Новая биржа = класс с `rubrics()` и `fetch_orders()` + запись в
  `exchanges/registry.py`.
- `exchanges/kwork/` — парсер kwork.ru: GET `https://kwork.ru/projects?c=<рубрика>&attr=<подрубрики>`,
  данные берутся из встроенного в HTML `window.stateData`.
  Проверка парсера вручную: `venv/bin/python -m exchanges.kwork.provider`.
- `watcher/watcher.py` — цикл опроса (интервал `POLL_INTERVAL` из `.env`),
  дедупликация через таблицу `seen_orders`. При самом первом запуске текущие
  заказы только помечаются, без рассылки.
- `storage/` — SQLite (`bot.db`): чаты, подписки, просмотренные заказы.
- `bot/` — хендлеры aiogram, клавиатуры меню, форматирование уведомлений.

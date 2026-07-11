# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Telegram bot (aiogram 3) that polls freelance exchanges for new orders and pushes notifications to chats. Currently only kwork.ru is wired up. No test suite exists.

## Running

```bash
cp .env.example .env   # fill in BOT_TOKEN
venv/bin/python main.py
```

Manual parser check (hits kwork.ru live, prints parsed orders instead of sending):
```bash
venv/bin/python -m exchanges.kwork.provider
```

Deployment is Docker-based, not the systemd unit in the repo root (`freelance-bot.service` is legacy/unused):
```bash
docker compose up -d --build   # rebuild + restart after any code change
docker logs freelance-bot --tail 50
```
The container mounts `./data:/app/data` and runs with `DB_PATH=data/bot.db` (`.env` sets `DB_PATH=bot.db` for local/non-Docker runs — these are two different SQLite files, don't confuse them when debugging state). There's a stale `bot.db` in the repo root from before Docker was introduced; the live database is `data/bot.db`.

`.env` keys: `BOT_TOKEN`, `POLL_INTERVAL` (seconds between exchange polls, default 300 — kept high with jitter to avoid tripping kwork's anti-bot rate limiting), `DB_PATH`, `SEED_CHAT_ID` (optional chat auto-registered on startup), `GROQ_API_KEY` (optional — free Groq API key for the draft-response feature; if unset, the draft button just replies that it's not configured instead of failing).

## Architecture

**Exchange abstraction** (`exchanges/base.py`): `BaseExchange` contract — `rubrics()` returns the category tree for menus/default subscriptions, `fetch_orders(rubric_id, attr_ids)` returns new-first `Order`s. Adding an exchange means implementing this contract and registering the instance in `exchanges/registry.py`.

**kwork provider** (`exchanges/kwork/provider.py`): GETs `https://kwork.ru/projects?c=<rubric>&attr=<subrubrics>` and extracts `window.stateData` embedded in the HTML response — there's no JSON API. `exchanges/kwork/categories.py` hardcodes the rubric/subrubric ID tree scraped from that state; if kwork changes its category structure these IDs need re-verifying (see the dated comment at the top of that file).

**Watcher loop** (`watcher/watcher.py`): the core polling loop, one iteration per `POLL_INTERVAL`. Key invariant: it polls exchanges and updates `seen_orders` for **every** registered chat, regardless of that chat's notification toggle — only the actual `send_order` call is gated on whether the chat is currently active. This is deliberate: if polling were skipped while a chat has notifications off, `seen_orders` would go stale and re-enabling notifications would dump the entire backlog as "new" orders at once. Don't reintroduce a check that skips polling based on the notify toggle.

On the very first run for an exchange (`seen_orders` empty for it), the watcher bootstraps silently — marks all currently-listed orders as seen without sending anything, so startup doesn't spam every existing order.

Requests to the exchange are deliberately throttled and randomized (`REQUEST_PAUSE` random pause between per-rubric requests, `INTERVAL_JITTER` random spread on the poll interval) to avoid tripping kwork's anti-bot rate limiting. Don't tighten these back down without a reason.

Orders are deduplicated per-exchange in `seen_orders` (not per-chat), and delivery within a poll cycle is deduped per `(chat_id, order_id)` since a chat can subscribe to overlapping rubric/subrubric combos.

**Storage** (`storage/`): `database.py` owns schema + connection (SQLite via aiosqlite) plus a `_migrate()` step run on every connect — `CREATE TABLE IF NOT EXISTS` doesn't add columns to a table that already exists, so new `chats`/`subscriptions` columns need an `ALTER TABLE ... ADD COLUMN` guarded by `except aiosqlite.OperationalError: pass` added there. `repository.py` has four repos — `ChatRepo` (registration, global notify toggle, per-chat silent/no-sound toggle), `SubscriptionRepo` (per-chat rubric/subrubric enable state), `SeenOrdersRepo` (dedup + periodic cleanup of old entries), `OrderCacheRepo` (title/description of delivered orders, keyed by exchange+order_id, so the draft-response button can look them up after the watcher's in-memory `Order` is gone — populated by the watcher on delivery, cleaned up on the same 30-day cadence as `seen_orders`).

**Bot layer** (`bot/`): `handlers/commands.py` handles `/start`, `/menu`, `/status`; `handlers/menu.py` handles the inline-menu callback tree (toggle notifications / sound / rubric / subrubric, generate a reply draft, navigate between menu levels) — all driven by the single `MenuCb` callback-data schema in `keyboards.py`. `notifications.py` formats and sends order messages (HTML parse mode): unescapes HTML entities from kwork's description text, strips/collapses whitespace, truncates long descriptions at a word boundary, and sends with `disable_notification` set per-chat from the silent toggle (watcher passes this in via `ChatRepo.silent_chat_ids()`).

**Draft responses** (`bot/draftgen.py`): each order notification has a "✍️ Черновик отклика" button. Tapping it calls the free Groq API (Llama 3.3 70B, OpenAI-compatible `groq` SDK) to draft a short bid response from the order's title/description, sent back as a separate reply message — actually submitting the response on kwork is always manual. This is deliberate: kwork's Terms of Service bans automated/bot responses and reserves the right to ban accounts for it (same reasoning behind the request throttling in the watcher), so only the low-stakes, read-only side (monitoring + drafting) is automated. Draft generation is on-demand (button tap), not automatic per order, to stay within Groq's free-tier limits.

## Notes

- `main.py` wires everything together: loads config, opens the DB, builds repos, registers `SEED_CHAT_ID` if set, starts the aiogram dispatcher and the watcher as a background task.
- Parse mode is HTML globally (`DefaultBotProperties(parse_mode=ParseMode.HTML)`); any user-supplied or scraped text going into a message must be `html.escape`d before interpolation.

## Keeping this file in sync

Whenever a change you make to the bot causes this file to no longer match reality (a described invariant, command, architecture note, or file path becomes stale), update CLAUDE.md in the same session — don't leave it for later.

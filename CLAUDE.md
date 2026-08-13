# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Telegram bot (aiogram 3) that polls freelance exchanges for new orders and pushes notifications to chats. Currently only kwork.ru is wired up.

## Running

```bash
cp .env.example .env   # fill in BOT_TOKEN
venv/bin/python main.py
```

Manual parser check (hits kwork.ru live, prints parsed orders instead of sending):
```bash
venv/bin/python -m exchanges.kwork.provider
```

## Tests

```bash
venv/bin/pip install -r requirements-dev.txt   # pytest, pytest-asyncio, ruff
venv/bin/pytest
venv/bin/ruff check .
```

pytest/ruff config lives in `pyproject.toml` (`asyncio_mode = "auto"`, so `async def test_...` needs no marker; `pythonpath = ["."]` so tests import `bot.*`/`watcher.*` without installing the project).

**Hard rule: no test may touch the network.** kwork has anti-bot protection and Groq has free-tier limits — a suite that hits either would go red for reasons unrelated to the code. `tests/conftest.py` enforces this with an autouse fixture that makes `aiohttp.ClientSession` and `groq.AsyncGroq` raise. Instead: monkeypatch `KworkExchange._get` to return `tests/fixtures/kwork_projects.html`, and pass a fake client to `generate_draft`.

Shared fixtures in `tests/conftest.py`: in-memory SQLite `conn` plus one fixture per repo, `FakeExchange` (configurable rubric tree, records which rubric/attrs were requested, can be told to raise via `fail_on`), `FakeBot` (collects sent messages; `broken_bot` raises on every send), `make_order` factory.

`tests/test_watcher.py::TestNotifyToggleDoesNotAffectPolling` guards the polling invariant described below — it's a regression suite for a bug that actually shipped, so don't delete those tests when refactoring the watcher.

The kwork fixture is a trimmed synthetic snapshot of the projects page. Note the caveat in its header comment: never write the state-variable name followed by `=` in that file's comments, or `STATE_RE` matches the comment instead of the data.

Local `venv` is Python 3.10 while the Docker image is 3.12 — CI (`.github/workflows/ci.yml`) runs the suite on both so the two don't drift; drop the `"3.10"` matrix entry once the venv is upgraded.

## CI/CD

`.github/workflows/ci.yml` runs on every PR and on push to `main`: ruff + pytest (matrix 3.10/3.12), a gitleaks history scan, and a `docker build` that is then scanned by trivy (report-only, `exit-code: 0`). No secrets are needed — the network ban in `tests/conftest.py` is what makes a green run possible without `BOT_TOKEN`/`GROQ_API_KEY`. Never add a live parser call (`python -m exchanges.kwork.provider`) to CI: kwork's anti-bot will 403 the shared runner IPs.

`.github/workflows/deploy.yml` runs on push to `main` (and manually via **Run workflow**): it builds the image, pushes it to `ghcr.io/mmmontov/freelance-bot` tagged `latest` + `sha-<commit>`, then SSHes to the server and runs `docker compose pull && up -d`. `docker-compose.yml` pins `image: ghcr.io/mmmontov/freelance-bot:${IMAGE_TAG:-latest}`, so the server never builds — it only pulls what CI already tested. The `build: .` key is kept so local `docker compose up -d --build` still works.

Details that are load-bearing in `deploy.yml`, don't "clean them up":
- `set -e` as the first line of the SSH script — `appleboy/ssh-action` dropped `script_stop` in v1.0.0, and without it the script's exit code is just the last command's, so a failed health check would still report a green deploy.
- `priority=300` on the `type=sha` tag rule — `metadata-action` picks the highest-priority tag for `outputs.version` (`raw` defaults to 200, `sha` to 100), and that output is what pins the deploy to a commit.
- `envs: IMAGE_TAG` — the action does not forward env vars to the remote shell on its own; without it a rollback silently deploys `latest`.
- `concurrency: deploy-production` with `cancel-in-progress: false` — the bot uses long polling, so two live containers on one token get `Conflict: terminated by other getUpdates`. Deploys queue, they never overlap or get cancelled mid-script.

Rollback is **Actions → Deploy → Run workflow** with a previous `sha-…` tag in the input — no rebuild involved. Each deploy also copies `data/bot.db` to `data/backup-<date>.db` and keeps the five most recent.

Manual deploy is still possible on the server (`docker compose up -d --build`), but it bypasses the tests and leaves the running image untagged — use it only when Actions is unavailable. `docker logs freelance-bot --tail 50` for logs.

## Runtime config

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

**Draft responses** (`bot/draftgen.py`): each order notification has a "✍️ Черновик отклика" button. Tapping it calls the free Groq API (Llama 3.3 70B, OpenAI-compatible `groq` SDK) to draft a short (150-250 char) bid response from the order's title/description, sent as a reply message with its own keyboard ("🔄 Перегенерировать" edits the same message in place with a new draft, "🗑 Удалить" removes it) — actually submitting the response on kwork is always manual. This is deliberate: kwork's Terms of Service bans automated/bot responses and reserves the right to ban accounts for it (same reasoning behind the request throttling in the watcher), so only the low-stakes, read-only side (monitoring + drafting) is automated. Draft generation is on-demand (button tap), not automatic per order, to stay within Groq's free-tier limits.

Style is steered by `data/style_profile.md` (optional, read fresh on every call — no rebuild needed to update it): the user's tech stack plus real order→response example pairs, appended to the system prompt so the model matches their tone/paragraph structure instead of writing generic AI boilerplate. Lives only in the `data/` volume (gitignored, same as the SQLite DB) since it's personal writing samples, not code — if this file is missing the bot falls back to the generic `SYSTEM_PROMPT`.

## Notes

- `main.py` wires everything together: loads config, opens the DB, builds repos, registers `SEED_CHAT_ID` if set, starts the aiogram dispatcher and the watcher as a background task.
- Parse mode is HTML globally (`DefaultBotProperties(parse_mode=ParseMode.HTML)`); any user-supplied or scraped text going into a message must be `html.escape`d before interpolation.

## Keeping this file in sync

Whenever a change you make to the bot causes this file to no longer match reality (a described invariant, command, architecture note, or file path becomes stale), update CLAUDE.md in the same session — don't leave it for later.

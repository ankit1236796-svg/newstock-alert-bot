# NewStock Alert Bot

Production-ready async architecture for a multi-user Telegram stock alert bot focused on Indian shopping websites.

This initial version intentionally **does not** implement Telegram commands or any shopping website scraping logic. It creates the scalable foundation needed to support Amazon, Flipkart, Croma, AJIO, Meesho, Zepto, Instamart, BigBasket, Savana, and future marketplaces.

## Stack

- Python 3.12
- aiogram 3.x for Telegram bot integration
- Playwright for future browser automation
- SQLite through `aiosqlite` for async persistence
- APScheduler for async recurring stock checks
- Pydantic Settings and `.env` for configuration

## Module layout

```text
app/
  bot/                         aiogram Bot and Dispatcher factories; command routers will be added later.
  core/                        typed settings loaded from environment variables and .env files.
  database/                    SQLite connection lifecycle, schema creation, and repository implementations.
  domain/entities/             pure typed dataclasses and enums for users, products, pincodes, and stock checks.
  domain/repositories/         repository protocols that keep business logic independent from SQLite.
  integrations/marketplaces/   shared marketplace adapter contracts for future website-specific integrations.
  observability/               structured logging setup for container-friendly production logs.
  services/browser/            Playwright browser session lifecycle for future scraping/checking workflows.
  services/notifications/      notification protocol for Telegram alert delivery.
  services/scheduler/          APScheduler setup and placeholder recurring stock-check job.
```

## Why each module exists

- `app/core/config.py` centralizes environment-backed configuration so deployment-specific values never leak into code.
- `app/observability/logging.py` configures key-value structured logs that are easy to parse in Docker, Kubernetes, and log aggregators.
- `app/database/connection.py` owns SQLite initialization, foreign-key enforcement, schema creation, and async connection lifecycle.
- `app/database/repositories.py` implements persistence behind repository interfaces, making it possible to replace SQLite or add caching without changing bot handlers or services.
- `app/domain/entities/models.py` defines framework-independent business objects for users, products, product pincodes, and stock checks.
- `app/domain/repositories/protocols.py` defines async repository contracts for dependency inversion and testability.
- `app/bot/factory.py` creates aiogram primitives without registering commands yet, keeping command implementation out of this architecture-only milestone.
- `app/integrations/marketplaces/base.py` defines request/result dataclasses plus the async marketplace adapter protocol without implementing any shopping website.
- `app/services/browser/session.py` isolates Playwright browser lifecycle so marketplace clients can share robust browser setup later.
- `app/services/scheduler/runner.py` wires APScheduler to an async recurring job with single-instance protection to avoid overlapping stock checks.
- `app/services/scheduler/jobs.py` contains a no-op stock-check placeholder until marketplace clients are implemented.
- `app/services/notifications/notifier.py` defines the alert-delivery contract that Telegram-specific notification code can satisfy later.

## Data model

- `users`: one row per Telegram user; `telegram_user_id` is unique for multi-user support.
- `products`: multiple tracked products per user, with marketplace, URL, display name, optional target price, and active flag.
- `product_pincodes`: multiple PIN codes per product, unique by `(product_id, pincode)`.
- `stock_checks`: append-only history of checks per product and PIN code for auditability and future analytics.

## Setup

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
playwright install chromium
python -m app
```

The app starts the database and scheduler only. Telegram commands and marketplace implementations are intentionally deferred.

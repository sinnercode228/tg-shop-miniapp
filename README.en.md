# Zernolist — a Telegram Mini App shop

[Русский](README.md) · **English**

A coffee and tea shop that opens right inside Telegram. The customer searches the catalog, applies a promo code, picks courier delivery or pickup, pays with Stars or on receipt, and then tracks the order status. Orders reach the admin in the bot, and the admin changes their status with buttons under the notification. The Zernolist shop doesn't exist; I made up the product range and the prices.

Demo in a regular browser: https://sinnercode228.github.io/tg-shop-miniapp/

<p>
  <img src="docs/screenshots/catalog.png" width="260" alt="Catalog">
  <img src="docs/screenshots/cart-dark.png" width="260" alt="Cart with a promo code, dark theme">
  <img src="docs/screenshots/stars-payment.png" width="260" alt="Demo Stars payment sheet">
</p>

A browser has no Telegram main button, so the page draws its own (`FallbackMainButton`). The demo has no backend: [`MockShopApi`](webapp/src/api/mock.ts) serves the data, orders are kept in `localStorage`, and statuses move forward on their own 30 seconds, 3 minutes and 15 minutes after checkout (for a Stars order, after payment). Instead of the native Stars payment sheet, you get an imitation (`DemoInvoiceSheet`); both components are in [`Chrome.tsx`](webapp/src/components/Chrome.tsx). The screenshots were taken in this mode, not in the Telegram client.

## Money is counted in kopecks

I keep every amount in whole kopecks, from [`shared/pricing.json`](shared/pricing.json) to the database columns. The Stars price is calculated from the order total with the discount and delivery applied: one Star costs 150 kopecks (`kopecksPerStar`), rounded up in the shop's favor. In [`domain/pricing.py`](bot/tgshop/domain/pricing.py) that's the integer division `-(-amount // rules.kopecks_per_star)`, with no floats.

The screenshots show a cart totaling 1862 ₽ and a payment sheet for 1242 Stars: 186200 / 150 = 1241.33, rounded up. A percentage discount is rounded down to a whole ruble: `ZERNO10` on 1503.45 ₽ gives 150 ₽, not 150.35. This promo code is capped at 1000 ₽.

The server doesn't use the price from the request. The cart item schema has no price field, and `OrderService._resolve` ([`services/orders.py`](bot/tgshop/services/orders.py)) takes the product, variant and price from the catalog:

> Resolve client items against the catalog. Client-side prices are never trusted.

The `test_client_supplied_prices_are_ignored` test in [`test_api.py`](bot/tests/test_api.py) sends a gaiwan with `"price": 1` and `total: 1` and checks that the order's `subtotal` equals the catalog's 129000 kopecks (1290 ₽).

The same logic exists in TypeScript in [`webapp/src/domain/pricing.ts`](webapp/src/domain/pricing.ts): the cart and the demo API compute prices with it, while the checkout screen in `http` mode gets the numbers from the server (`POST /api/quote`). So that the two implementations can't drift apart unnoticed, [`shared/pricing-cases.json`](shared/pricing-cases.json) holds 9 test vectors: the free delivery threshold (it's based on the amount after discount), the discount cap, an unknown promo code, an empty string instead of a promo code, and so on. Both pytest ([`test_pricing.py`](bot/tests/test_pricing.py)) and vitest ([`pricing.contract.test.ts`](webapp/src/domain/pricing.contract.test.ts)) run them. In TS, Stars and the discount are computed with `Math.ceil`/`Math.floor` on top of regular division: these numbers are only for the cart and the demo, and the server computes the amount to pay in integers.

## Payment: from `POST /api/orders` to `successful_payment`

1. The Mini App sends `POST /api/orders` with an `Authorization: tma <initData>` header ([`api/deps.py`](bot/tgshop/api/deps.py)).
2. The server validates initData, recalculates the price and creates an order in the `awaiting_payment` status, with the amount in Stars locked in (`stars_amount`).
3. The same response carries an invoice link from `createInvoiceLink`: currency `XTR`, payload `order:<id>` ([`payments/stars.py`](bot/tgshop/payments/stars.py)).
4. The Mini App opens it with `Telegram.WebApp.openInvoice` ([`api/http.ts`](webapp/src/api/http.ts)). If the sheet gets closed, the order page still has a pay button: while the order is in `awaiting_payment`, it gets a new link through `POST /api/orders/{id}/invoice` ([`routes/orders.py`](bot/tgshop/api/routes/orders.py)).
5. Telegram sends `pre_checkout_query`, and the bot has 10 seconds to answer. `check_payment` verifies the currency, that the person paying owns the order, that the order is still awaiting payment, and that the amount matches `stars_amount`.
6. `successful_payment` arrives. `mark_paid` repeats the same check, saves `telegram_payment_charge_id` (refunds are made with it later) and moves the order to `paid`. Only now do the admins get the new-order notification; pay-on-receipt orders reach them right away.

Telegram may deliver the same update more than once. `mark_paid` first checks whether this charge id is already recorded on the order, and if it is, returns the order right away. In `test_full_stars_payment_flow` ([`test_order_service.py`](bot/tests/test_order_service.py)), `mark_paid` is called a second time with the same charge id, and no second notification goes to the admins. The `telegram_payment_charge_id` column is declared with `unique=True` ([`db/models.py`](bot/tgshop/db/models.py)), so one payment can't be recorded against two orders.

Sometimes the customer has paid, but the order was cancelled in the meantime. Then the check in `mark_paid` fails, and the service calls `refundStarPayment` on its own, without waiting for support. The bot tells the customer their Stars have been returned. `test_payment_for_cancelled_order_is_refunded_automatically` covers this scenario.

Statuses are defined as an explicit graph in [`domain/status.py`](bot/tgshop/domain/status.py); `ensure_transition` rejects everything else. The diagram follows the module docstring:

```text
awaiting_payment ──► paid ──► confirmed ──► in_delivery ──────► completed
      │                │          │    └──► ready_for_pickup ─► completed
      ▼                ▼          ▼
  cancelled        refunded   cancelled / refunded
new ──► confirmed …          (pay on receipt, no payment step)
```

On top of the graph, `allowed_transitions` takes the payment method into account: an order paid with Stars can't simply be cancelled, only refunded (`refunded`); a pay-on-receipt order can't be refunded; and `paid` can't be set by hand at all: it only comes from the payment flow. The buttons under the admin notification are built from `allowed_transitions` ([`keyboards.py`](bot/tgshop/bot/keyboards.py)), so none of them offers an invalid action.

Every transition is written to `order_events` with a timestamp, and the Mini App draws the status timeline from these records. SQLite loses `tzinfo` on read, so every `datetime` in the models goes through the `UTCDateTime` type ([`db/models.py`](bot/tgshop/db/models.py)): it returns UTC and won't let a naive datetime into the database.

I register the payments router with the dispatcher first ([`factory.py`](bot/tgshop/bot/factory.py)). There are no other `pre_checkout_query` handlers right now; the order is a safeguard in case one shows up in another router and intercepts the query.

If the bot is blocked or the network is flaky, [`TelegramNotifier`](bot/tgshop/bot/notifier.py) logs the `TelegramAPIError` and doesn't re-raise it. The order still goes through; only the notification doesn't arrive.

Not done yet: an unpaid order sits in `awaiting_payment` until an admin cancels it by hand (`/status <id> cancelled`). [`OrderRepository.get`](bot/tgshop/db/repository.py) with `for_update=True` calls `with_for_update()`, but SQLAlchemy doesn't generate `FOR UPDATE` for SQLite, so the order row isn't locked for the duration of the transaction. A manual refund (`/refund` or the admin's button) calls `refundStarPayment` inside an open transaction (`OrderService.refund`), and if the commit fails after Telegram responds, the Stars will already be returned while the order status stays the same.

## The initData signature and other people's orders

[`security/init_data.py`](bot/tgshop/security/init_data.py) checks the signature with the algorithm from the Telegram docs: the secret key is the HMAC-SHA256 of the bot token with the key `"WebAppData"`, then comes an HMAC of the sorted `key=value` pairs without `hash`, and the result is compared with the received one via `hmac.compare_digest`. initData is also rejected if:

- it's older than 24 hours (`INIT_DATA_TTL` sets the lifetime, and the setting won't accept less than 60 seconds);
- `auth_date` is more than 60 seconds in the future (`auth_date_in_future`);
- a key is repeated in the string (Telegram doesn't build such strings);
- it has no `user`: the shop needs a customer.

The `test_algorithm_matches_telegram_docs_step_by_step` test in [`test_init_data.py`](bot/tests/test_init_data.py) computes the expected hash by following the docs step by step, directly with `hmac` and `hashlib`, and only then compares `compute_hash` against it. The test next to it pins down that the `signature` field from Bot API 8.0 is part of the data-check string: only `hash` is excluded. The code doesn't verify the Ed25519 signature itself, only the HMAC.

Someone else's order isn't returned by id, and the response is the same as for an order that doesn't exist: 404 `not_found`. That way `get_for_user` doesn't let anyone find out which orders exist by enumerating ids.

## Telegram theme and buttons

[`telegram/sdk.ts`](webapp/src/telegram/sdk.ts) copies `themeParams` into `--tg-*` CSS variables, which the Tailwind tokens are built on; on `themeChanged` the variables are rewritten. Outside Telegram, [`index.css`](webapp/src/index.css) sets them based on `prefers-color-scheme`.

Inside Telegram, `useMainButton` from [`telegram/hooks.ts`](webapp/src/telegram/hooks.ts) drives the native `MainButton`; in a browser it puts the same state into a zustand store, and `FallbackMainButton` renders it from there. `useBackButton` shows the `BackButton` while the screen is mounted. In Telegram, vibration goes through `HapticFeedback` (WebApp 6.1+); in a browser, `navigator.vibrate` is only called after a real user gesture (`navigator.userActivation.hasBeenActive`).

## Running it yourself

The Mini App in [`webapp/`](webapp) is built with React 19, Vite, TypeScript, Tailwind CSS 4 and zustand. In [`bot/`](bot), aiogram 3 and FastAPI run in one process, and the database is accessed through SQLAlchemy 2 (async) and aiosqlite. The catalog and pricing rules live in [`shared/`](shared), and both sides read them. Each group of commands below is run from the repository root.

```bash
# Demo without a backend, same as on GitHub Pages
cd webapp && npm ci && npm run dev    # http://localhost:5173

# Bot + API
cd bot
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env           # BOT_TOKEN from @BotFather, ADMIN_IDS, WEBAPP_URL
python -m tgshop --mode all    # long polling + API on :8080; there's also --mode bot and --mode api

# Mini App on top of the real API (Vite proxies /api to :8080)
cd webapp && VITE_API_MODE=http npm run dev
```

The other variables (`DATABASE_URL`, `API_HOST`, `API_PORT`, `CORS_ORIGINS`, `INIT_DATA_TTL`, `STARS_ENABLED`, `LOG_LEVEL`) are listed in [`bot/.env.example`](bot/.env.example). In `http` mode, the catalog and price calculation (`/api/catalog`, `/api/quote`) work in a browser, but orders require initData: without it the API returns 401, so you can only place an order from the Telegram client.

Everything together in Docker: `cp bot/.env.example bot/.env`, fill in `BOT_TOKEN`, then `docker compose up --build`. The API listens on `:8080`; nginx serves the Mini App on `:8081` and proxies `/api`. Telegram only opens Mini Apps over HTTPS, so to test in the client you need a tunnel or a reverse proxy, and its address goes into `WEBAPP_URL`.

## 107 + 36 tests

```bash
(cd bot && pytest --cov)       # 107 tests, 85% coverage
(cd webapp && npm test)        # 36 tests, vitest
```

[CI](.github/workflows/ci.yml) runs both suites along with ruff, mypy strict and eslint on Python 3.12 and 3.14 and Node 22.

pytest covers initData, pricing and the contract vectors, the status graph, the order service with a fake payment gateway (`FakePayments`), the HTTP API through httpx, and the bot handlers. The handlers are tested without aiogram mocks: real `Update` objects go through a real `Dispatcher` with routing, filters and DI, and in place of the network there's a `RecordingSession` that records every Bot API call ([`tests/test_bot.py`](bot/tests/test_bot.py)).

vitest: the cart, search, money formatting, the demo API, the same 9 pricing vectors, and three UI scenarios in jsdom on top of the mock API. In Node 25, Node's own global `localStorage` shadows the jsdom one, so [`src/test/setup.ts`](webapp/src/test/setup.ts) puts an in-memory store in its place.

---

Built by Грешный Котик (sinnercode). I take freelance work like this: Telegram [@sinnercode](https://t.me/sinnercode). License: [MIT](LICENSE).

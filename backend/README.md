# Awaz backend

Nest.js + PostgreSQL service that holds the menu, saves orders, logs calls and
alerts the restaurant on Telegram. The voice agent talks to it over HTTP; staff
use the dashboard at `/dashboard`.

Prices are always computed here from the menu. The AI only sends item names
(`slug`) and quantities, so a misheard number can never change what a customer
pays, and any extra field such as a price is rejected.

## Endpoints

| Method and path | Who | What |
| --- | --- | --- |
| `GET /health` | anyone | Service and database status |
| `GET /dashboard` | staff | Dashboard page (asks for `ADMIN_TOKEN`) |
| `GET /menu` | agent, staff | Menu with prices and aliases |
| `PATCH /menu/:id` | staff | Mark sold out (`available`) or change `priceAfn` |
| `POST /orders/quote` | agent, staff | Exact totals for a cart, nothing saved |
| `POST /orders` | agent | Save a confirmed order (`status: new`) or a callback request |
| `GET /orders`, `GET /orders/:id` | staff | Orders with their items |
| `PATCH /orders/:id/status` | staff | `accepted`, `delivered`, `cancelled` |
| `POST /calls` | agent | Call log: transcript, duration, tokens, estimated cost |
| `GET /calls`, `GET /stats` | staff | Call logs and the investor numbers |

The agent authenticates with the `x-agent-key: <AGENT_API_KEY>` header; staff
with `Authorization: Bearer <ADMIN_TOKEN>`.

## Run locally

```bash
npm install            # use npm 11 if npm 10 fails: npx npm@11 install
export DATABASE_URL=postgres://awaz:awaz@localhost:5432/awaz
export AGENT_API_KEY=change-me-at-least-16-chars
export ADMIN_TOKEN=change-me-too-at-least-16-chars
npm run start:dev
```

Migrations in `./drizzle` run automatically at startup, and the sample Herat
menu is inserted when the menu table is empty (`SEED_SAMPLE_MENU=false` turns
that off). After changing `src/db/schema.ts`, run `npm run db:generate` to
create the next migration.

## Tests

```bash
npm test                                   # unit tests, no database needed
TEST_DATABASE_URL=postgres://awaz:awaz@localhost:5432/awaz_test npm run test:e2e
```

The e2e tests wipe the database they are given, so point them at a throwaway
one.

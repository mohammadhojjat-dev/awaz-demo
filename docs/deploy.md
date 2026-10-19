# Deploy to a VPS

This puts the whole demo online on one server: PostgreSQL, the backend, the
voice agent, and Caddy for HTTPS. About 30 minutes.

## What you need

- A VPS with a public IP. Contabo Cloud VPS 20 (6 vCPU, 12 GB RAM, about
  €7/month) is plenty; no GPU is needed because Gemini does the AI work.
  Ubuntu 24.04 is assumed below.
- A domain or subdomain, e.g. `order.awaz.af`, with an **A record** pointing
  at the server's IP.
- A Gemini API key from <https://aistudio.google.com/apikey>. Use a paid
  (billing-enabled) key for real callers: the free tier has low limits and
  Google may use free-tier data to improve its products.

## 1. Prepare the server

```bash
ssh root@YOUR_SERVER_IP
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh

# Firewall: SSH, HTTP/HTTPS, and UDP for call audio (WebRTC picks a port per call).
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 10000:65535/udp
ufw enable
```

Ports 3000 (backend) and 7860 (agent) stay closed to the internet; Caddy
reaches them on `127.0.0.1`.

## 2. Get the code and configure it

```bash
git clone https://github.com/mohammadhojjat-dev/awaz-demo.git
cd awaz-demo
cp .env.example .env
nano .env
```

Fill in at least `GOOGLE_API_KEY`, `DOMAIN`, `POSTGRES_PASSWORD`,
`AGENT_API_KEY` and `ADMIN_TOKEN`. Generate each secret with
`openssl rand -hex 24`. Set `RESTAURANT_NAME` to the pilot restaurant.

For Telegram alerts: talk to [@BotFather](https://t.me/BotFather), create a
bot, copy its token into `TELEGRAM_BOT_TOKEN`, add the bot to the restaurant's
group, send any message there, open
`https://api.telegram.org/bot<TOKEN>/getUpdates` and copy the group's
`chat.id` (it starts with `-100`) into `TELEGRAM_CHAT_ID`.

## 3. Start

```bash
docker compose up -d --build
docker compose ps          # all four services should be "running" or "healthy"
docker compose logs -f agent
```

Then open:

- `https://YOUR_DOMAIN/order` to place a test call,
- `https://YOUR_DOMAIN/dashboard` and log in with `ADMIN_TOKEN` to see orders,
  calls, completion rate and cost per call.

The sample Herat menu is inserted on first start. To use the real menu, edit
`backend/src/db/sample-menu.ts` (and `agent/sample_menu.json`) before the first
start, or change prices and mark items sold out from the API:

```bash
# Run in the project folder; reads ADMIN_TOKEN from .env into this shell.
export ADMIN_TOKEN="$(grep '^ADMIN_TOKEN=' .env | cut -d= -f2-)"
curl -X PATCH https://YOUR_DOMAIN/menu/1 \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "content-type: application/json" \
  -d '{"priceAfn": 280, "available": true}'
```

## Updating

```bash
git pull
docker compose up -d --build
```

Database migrations run automatically when the backend starts.

## Backups

```bash
docker compose exec postgres pg_dump -U awaz awaz > backup-$(date +%F).sql
```

## If something is wrong

| Symptom | Check |
| --- | --- |
| Page loads but the call never connects | UDP ports open in `ufw` and in Contabo's firewall panel; `docker compose logs agent` |
| "میکروفون در دسترس نیست" | The page must be opened over `https://`; allow the microphone in the browser |
| Agent connects, then hangs up at once | `GOOGLE_API_KEY` wrong or out of quota: `docker compose logs agent` shows the Gemini error |
| The agent says the ordering system is unavailable | The backend is down: `docker compose logs backend` |
| No Telegram message | `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID`; the backend log prints the message it would have sent |
| Certificate errors | The domain's A record must point at the server before Caddy starts |

# WhatsApp calls

Customers can call the restaurant's WhatsApp Business number and talk to the
agent. Calls a customer starts are free for the business, and the caller's
number arrives with the call, so the agent does not ask for it.

The agent already supports this through Pipecat's WhatsApp transport. What it
needs is Meta's approval and four values in `.env`.

## 1. Get WhatsApp Business Platform access

1. Create a Meta Business account and verify the business at
   <https://business.facebook.com>. If verifying an Afghan business is slow,
   use your UK company.
2. At <https://developers.facebook.com>, create an app of type **Business**
   and add the **WhatsApp** product.
3. Add and verify the phone number customers will call. It must not be in use
   in the regular WhatsApp or WhatsApp Business app.
4. In WhatsApp Manager, open **Phone numbers → your number → Calls** and turn
   on **Allow voice calls**.

## 2. Copy the values into `.env`

| `.env` name | Where to find it |
| --- | --- |
| `WHATSAPP_TOKEN` | A permanent token from a System User with `whatsapp_business_messaging` permission (Business settings → System users). Temporary tokens expire in 24 hours. |
| `WHATSAPP_PHONE_NUMBER_ID` | App dashboard → WhatsApp → API setup, "Phone number ID" |
| `WHATSAPP_APP_SECRET` | App dashboard → App settings → Basic → App secret |
| `WHATSAPP_WEBHOOK_VERIFICATION_TOKEN` | Any random string you choose, e.g. `openssl rand -hex 16` |

Restart the agent: `docker compose up -d agent`. When `WHATSAPP_TOKEN` is set
the agent starts with WhatsApp calling switched on.

## 3. Point Meta's webhook at the agent

In the app dashboard → WhatsApp → Configuration → Webhook:

- **Callback URL**: `https://YOUR_DOMAIN/whatsapp`
- **Verify token**: the same value as `WHATSAPP_WEBHOOK_VERIFICATION_TOKEN`
- Subscribe to the **calls** field.

## 4. Test

Call the business number from WhatsApp on a phone. The order shows up on the
dashboard with channel "واتس‌اپ" and the caller's number filled in.

Notes:

- Test numbers in development mode last 90 days; use a real, verified number
  for the pilot.
- Every incoming call event refreshes WhatsApp's 24-hour messaging window, so
  you may also send the customer a text receipt later (not built yet).
- Source: [Pipecat WhatsApp guide](https://docs.pipecat.ai/guides/features/whatsapp),
  [Meta Calling API pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/calling/pricing/).

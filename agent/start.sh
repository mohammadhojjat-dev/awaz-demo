#!/bin/sh
# Starts the voice agent. WhatsApp calling is switched on when its token is set.
set -e
EXTRA=""
if [ -n "$WHATSAPP_TOKEN" ]; then
  EXTRA="--whatsapp"
fi
exec python bot.py -t webrtc --host "${AGENT_HOST:-127.0.0.1}" --port "${AGENT_PORT:-7860}" $EXTRA

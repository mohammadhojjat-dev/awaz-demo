import { Inject, Injectable, Logger } from '@nestjs/common';
import { APP_CONFIG, type AppConfig } from '../config.js';
import type { Order, OrderItem } from '../db/schema.js';

const CHANNEL_LABELS: Record<string, string> = {
  web: 'دکمه تماس وب',
  whatsapp: 'واتس‌اپ',
  phone: 'تلفن',
  eval: 'آزمایش',
};

/** Escapes text for Telegram's HTML parse mode. */
export function escapeHtml(text: string): string {
  return text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** Builds the Dari message staff see in Telegram for a new order or callback. */
export function formatOrderMessage(order: Order, items: OrderItem[], restaurantName: string): string {
  const isCallback = order.status === 'callback';
  const lines: string[] = [];
  lines.push(
    isCallback
      ? `📞 <b>لطفاً به مشتری زنگ بزنید</b> — سفارش #${order.code}`
      : `🆕 <b>سفارش جدید #${order.code}</b>`,
  );
  lines.push(escapeHtml(restaurantName));
  lines.push('');
  if (order.customerName) lines.push(`مشتری: ${escapeHtml(order.customerName)}`);
  if (order.customerPhone) lines.push(`شماره: ${escapeHtml(order.customerPhone)}`);
  if (order.address) lines.push(`آدرس: ${escapeHtml(order.address)}`);
  if (order.landmark) lines.push(`نشانی نزدیک: ${escapeHtml(order.landmark)}`);
  if (items.length > 0) {
    lines.push('');
    for (const item of items) {
      const note = item.note ? ` (${escapeHtml(item.note)})` : '';
      lines.push(`• ${item.quantity} × ${escapeHtml(item.nameFa)}${note} = ${item.lineTotalAfn} افغانی`);
    }
    lines.push(`هزینه انتقال: ${order.deliveryFeeAfn} افغانی`);
    lines.push(`<b>مجموع: ${order.totalAfn} افغانی</b>`);
  }
  if (isCallback && order.callbackReason) {
    lines.push('');
    lines.push(`دلیل: ${escapeHtml(order.callbackReason)}`);
  }
  if (order.notes) lines.push(`یادداشت: ${escapeHtml(order.notes)}`);
  lines.push('');
  lines.push(`کانال: ${CHANNEL_LABELS[order.channel] ?? escapeHtml(order.channel)}`);
  return lines.join('\n');
}

/**
 * Sends order alerts to the restaurant's Telegram chat. Without a bot token
 * and chat id it only logs, so the demo still works before Telegram is set up.
 * Sending never throws: an order is saved even if Telegram is down.
 */
@Injectable()
export class TelegramService {
  private readonly logger = new Logger(TelegramService.name);

  constructor(@Inject(APP_CONFIG) private readonly config: AppConfig) {}

  get enabled(): boolean {
    return Boolean(this.config.telegramBotToken && this.config.telegramChatId);
  }

  async notifyOrder(order: Order, items: OrderItem[]): Promise<boolean> {
    const text = formatOrderMessage(order, items, this.config.restaurantName);
    if (!this.enabled) {
      this.logger.log(`Telegram not configured; order #${order.code} would be sent as:\n${text}`);
      return false;
    }
    try {
      const response = await fetch(
        `https://api.telegram.org/bot${this.config.telegramBotToken}/sendMessage`,
        {
          method: 'POST',
          headers: { 'content-type': 'application/json' },
          body: JSON.stringify({
            chat_id: this.config.telegramChatId,
            text,
            parse_mode: 'HTML',
            disable_web_page_preview: true,
          }),
          signal: AbortSignal.timeout(10_000),
        },
      );
      if (!response.ok) {
        this.logger.error(`Telegram returned ${response.status}: ${await response.text()}`);
        return false;
      }
      return true;
    } catch (error) {
      this.logger.error(`Telegram send failed: ${(error as Error).message}`);
      return false;
    }
  }
}

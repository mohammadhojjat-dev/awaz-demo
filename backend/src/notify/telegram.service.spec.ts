import type { AppConfig } from '../config.js';
import type { Order, OrderItem } from '../db/schema.js';
import { escapeHtml, formatOrderMessage, TelegramService } from './telegram.service.js';

const baseOrder: Order = {
  id: 7,
  code: '1007',
  sessionId: 's1',
  channel: 'whatsapp',
  status: 'new',
  customerName: 'احمد <b>',
  customerPhone: '+93799000000',
  address: 'جاده محبس',
  landmark: 'نزدیک مسجد',
  notes: null,
  callbackReason: null,
  subtotalAfn: 500,
  deliveryFeeAfn: 50,
  totalAfn: 550,
  etaMinutes: 40,
  createdAt: new Date(),
  updatedAt: new Date(),
};
const items: OrderItem[] = [
  { id: 1, orderId: 7, menuItemId: 1, nameFa: 'قابلی پلو', unitPriceAfn: 250, quantity: 2, note: 'تند', lineTotalAfn: 500 },
];

const config = (overrides: Partial<AppConfig> = {}): AppConfig => ({
  port: 3000,
  databaseUrl: 'postgres://x',
  agentApiKey: 'a'.repeat(16),
  adminToken: 'b'.repeat(16),
  restaurantName: 'رستوران نمونه',
  deliveryFeeAfn: 50,
  etaMinutes: 40,
  telegramBotToken: null,
  telegramChatId: null,
  seedSampleMenu: true,
  ...overrides,
});

describe('formatOrderMessage', () => {
  it('lists items, totals and escapes caller text', () => {
    const text = formatOrderMessage(baseOrder, items, 'رستوران نمونه');
    expect(text).toContain('سفارش جدید #1007');
    expect(text).toContain('2 × قابلی پلو (تند) = 500 افغانی');
    expect(text).toContain('مجموع: 550 افغانی');
    expect(text).toContain('احمد &lt;b&gt;');
    expect(text).toContain('واتس‌اپ');
  });

  it('marks callbacks and includes the reason', () => {
    const text = formatOrderMessage(
      { ...baseOrder, status: 'callback', callbackReason: 'صدا واضح نبود' },
      [],
      'رستوران نمونه',
    );
    expect(text).toContain('لطفاً به مشتری زنگ بزنید');
    expect(text).toContain('دلیل: صدا واضح نبود');
    expect(text).not.toContain('مجموع');
  });

  it('escapes HTML special characters', () => {
    expect(escapeHtml('a & <b>')).toBe('a &amp; &lt;b&gt;');
  });
});

describe('TelegramService', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('only logs when Telegram is not configured', async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    const service = new TelegramService(config());
    expect(await service.notifyOrder(baseOrder, items)).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('sends to the configured chat and never throws on failure', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);
    const service = new TelegramService(config({ telegramBotToken: 'TOKEN', telegramChatId: '-100' }));
    expect(await service.notifyOrder(baseOrder, items)).toBe(true);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.telegram.org/botTOKEN/sendMessage');
    expect(JSON.parse(init.body)).toMatchObject({ chat_id: '-100', parse_mode: 'HTML' });

    fetchMock.mockRejectedValue(new Error('network down'));
    expect(await service.notifyOrder(baseOrder, items)).toBe(false);
  });
});

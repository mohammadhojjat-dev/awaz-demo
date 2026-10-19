/**
 * End-to-end tests against a real PostgreSQL database.
 *
 * Set TEST_DATABASE_URL to an empty database you don't mind wiping, e.g.
 *   TEST_DATABASE_URL=postgres://awaz:awaz@localhost:5432/awaz_test npm run test:e2e
 * Without it these tests are skipped.
 */
import type { INestApplication } from '@nestjs/common';
import { Test } from '@nestjs/testing';
import pg from 'pg';
import request from 'supertest';
import { configureApp } from '../src/app.setup.js';

const databaseUrl = process.env.TEST_DATABASE_URL;
const AGENT = 'test-agent-key-0123456789';
const ADMIN = 'test-admin-token-0123456789';

describe.skipIf(!databaseUrl)('Awaz backend (e2e)', () => {
  let app: INestApplication;
  const agent = () => ({ 'x-agent-key': AGENT });
  const admin = () => ({ authorization: `Bearer ${ADMIN}` });

  beforeAll(async () => {
    const client = new pg.Client({ connectionString: databaseUrl });
    await client.connect();
    await client.query('drop schema if exists public cascade; create schema public; drop schema if exists drizzle cascade;');
    await client.end();

    Object.assign(process.env, {
      DATABASE_URL: databaseUrl,
      AGENT_API_KEY: AGENT,
      ADMIN_TOKEN: ADMIN,
      DELIVERY_FEE_AFN: '50',
      ETA_MINUTES: '40',
      TELEGRAM_BOT_TOKEN: '',
      SEED_SAMPLE_MENU: 'true',
    });
    const { AppModule } = await import('../src/app.module.js');
    const moduleRef = await Test.createTestingModule({ imports: [AppModule] }).compile();
    app = moduleRef.createNestApplication();
    configureApp(app);
    await app.init();
  });

  afterAll(async () => {
    await app?.close();
  });

  it('reports health', async () => {
    await request(app.getHttpServer()).get('/health').expect(200, { ok: true, database: true });
  });

  it('seeds the sample menu and protects it', async () => {
    await request(app.getHttpServer()).get('/menu').expect(401);
    const res = await request(app.getHttpServer()).get('/menu').set(agent()).expect(200);
    expect(res.body.length).toBeGreaterThanOrEqual(10);
    expect(res.body[0]).toMatchObject({ slug: 'qabuli-palaw', nameFa: 'قابلی پلو', priceAfn: 250 });
  });

  it('rejects an empty menu update', async () => {
    await request(app.getHttpServer()).patch('/menu/1').set(admin()).send({}).expect(400);
  });

  it('quotes a cart with server-side prices', async () => {
    const res = await request(app.getHttpServer())
      .post('/orders/quote')
      .set(agent())
      .send({ items: [{ slug: 'qabuli-palaw', quantity: 2 }, { slug: 'doogh', quantity: 1 }] })
      .expect(200);
    expect(res.body).toMatchObject({ subtotalAfn: 550, deliveryFeeAfn: 50, totalAfn: 600 });
  });

  it('rejects unknown items with a code the agent can act on', async () => {
    const res = await request(app.getHttpServer())
      .post('/orders/quote')
      .set(agent())
      .send({ items: [{ slug: 'pizza', quantity: 1 }] })
      .expect(400);
    expect(res.body).toMatchObject({ code: 'unknown_item', slug: 'pizza' });
  });

  it('rejects fields it does not know, such as a price from the AI', async () => {
    await request(app.getHttpServer())
      .post('/orders/quote')
      .set(agent())
      .send({ items: [{ slug: 'doogh', quantity: 1, priceAfn: 1 }] })
      .expect(400);
  });

  it('creates an order once per call session', async () => {
    const body = {
      sessionId: 'session-1',
      channel: 'web',
      status: 'new',
      customerName: 'احمد',
      customerPhone: '0799000000',
      address: 'جاده محبس، کوچه دوم',
      landmark: 'نزدیک مسجد جامع',
      items: [{ slug: 'mantu', quantity: 1, note: 'بدون سیر' }],
    };
    const first = await request(app.getHttpServer()).post('/orders').set(agent()).send(body).expect(201);
    expect(first.body).toMatchObject({ status: 'new', totalAfn: 250, etaMinutes: 40, created: true, telegramSent: false });
    expect(first.body.code).toBe(String(1000 + first.body.id));

    const again = await request(app.getHttpServer()).post('/orders').set(agent()).send(body).expect(201);
    expect(again.body).toMatchObject({ id: first.body.id, created: false });

    const list = await request(app.getHttpServer()).get('/orders').set(admin()).expect(200);
    expect(list.body).toHaveLength(1);
    expect(list.body[0].items[0]).toMatchObject({ nameFa: 'منتو', quantity: 1, note: 'بدون سیر' });
  });

  it('requires name and address for a confirmed order', async () => {
    await request(app.getHttpServer())
      .post('/orders')
      .set(agent())
      .send({ sessionId: 'session-2', channel: 'web', status: 'new', items: [{ slug: 'naan', quantity: 2 }] })
      .expect(400);
  });

  it('accepts a callback request without items', async () => {
    const res = await request(app.getHttpServer())
      .post('/orders')
      .set(agent())
      .send({ sessionId: 'session-3', channel: 'whatsapp', status: 'callback', items: [], callbackReason: 'صدا واضح نبود', customerPhone: '+93700111222' })
      .expect(201);
    expect(res.body).toMatchObject({ status: 'callback', totalAfn: 0, etaMinutes: null });
  });

  it('lets staff move an order through its statuses', async () => {
    const [order] = (await request(app.getHttpServer()).get('/orders').set(admin())).body;
    const res = await request(app.getHttpServer())
      .patch(`/orders/${order.id}/status`)
      .set(admin())
      .send({ status: 'accepted' })
      .expect(200);
    expect(res.body.status).toBe('accepted');
    await request(app.getHttpServer()).patch(`/orders/${order.id}/status`).set(agent()).send({ status: 'delivered' }).expect(401);
  });

  it('records calls and reports investor stats', async () => {
    const started = new Date('2026-10-15T10:00:00Z');
    const call = (sessionId: string, outcome: string, seconds: number, cost: number) => ({
      sessionId,
      channel: 'web',
      outcome,
      startedAt: started.toISOString(),
      endedAt: new Date(started.getTime() + seconds * 1000).toISOString(),
      transcript: [
        { role: 'assistant', text: 'سلام، چه میل دارید؟' },
        { role: 'user', text: 'یک قابلی پلو' },
      ],
      llmPromptTokens: 3000,
      llmCompletionTokens: 120,
      ttsCharacters: 400,
      estCostUsd: cost,
    });
    await request(app.getHttpServer()).post('/calls').set(agent()).send(call('c1', 'ordered', 120, 0.03)).expect(201);
    await request(app.getHttpServer()).post('/calls').set(agent()).send(call('c2', 'callback', 60, 0.01)).expect(201);
    // A repeated report for the same session replaces the first one.
    await request(app.getHttpServer()).post('/calls').set(agent()).send(call('c2', 'callback', 60, 0.01)).expect(201);

    const stats = await request(app.getHttpServer()).get('/stats').set(admin()).expect(200);
    expect(stats.body).toMatchObject({ calls: 2, ordered: 1, callbacks: 1, completionRate: 0.5, avgDurationSec: 90 });
    expect(stats.body.avgCostUsd).toBeCloseTo(0.02, 5);

    const calls = await request(app.getHttpServer()).get('/calls').set(admin()).expect(200);
    expect(calls.body[0].transcript[1]).toEqual({ role: 'user', text: 'یک قابلی پلو' });
  });

  it('serves the dashboard page', async () => {
    const res = await request(app.getHttpServer()).get('/dashboard').expect(200);
    expect(res.text).toContain('داشبورد سفارش‌های تلفنی');
  });
});

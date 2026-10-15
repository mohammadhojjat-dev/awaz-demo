import {
  boolean,
  index,
  integer,
  jsonb,
  numeric,
  pgTable,
  serial,
  text,
  timestamp,
} from 'drizzle-orm/pg-core';

/** One dish or drink the restaurant sells. Prices are whole afghanis. */
export const menuItems = pgTable('menu_items', {
  id: serial('id').primaryKey(),
  slug: text('slug').notNull().unique(),
  nameFa: text('name_fa').notNull(),
  nameEn: text('name_en').notNull(),
  category: text('category').notNull(),
  priceAfn: integer('price_afn').notNull(),
  /** Other ways callers say this item; fed to speech recognition as hints. */
  aliases: jsonb('aliases').$type<string[]>().notNull().default([]),
  available: boolean('available').notNull().default(true),
  sortOrder: integer('sort_order').notNull().default(0),
});

/**
 * One order. `status` moves new -> accepted -> delivered, or ends in
 * `callback` when the agent hands the caller to staff, or `cancelled`.
 */
export const orders = pgTable(
  'orders',
  {
    id: serial('id').primaryKey(),
    code: text('code').notNull().unique(),
    sessionId: text('session_id').notNull(),
    channel: text('channel').notNull(),
    status: text('status').notNull(),
    customerName: text('customer_name'),
    customerPhone: text('customer_phone'),
    address: text('address'),
    landmark: text('landmark'),
    notes: text('notes'),
    callbackReason: text('callback_reason'),
    subtotalAfn: integer('subtotal_afn').notNull(),
    deliveryFeeAfn: integer('delivery_fee_afn').notNull(),
    totalAfn: integer('total_afn').notNull(),
    etaMinutes: integer('eta_minutes'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
    updatedAt: timestamp('updated_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index('orders_created_at_idx').on(t.createdAt), index('orders_session_idx').on(t.sessionId)],
);

/** A line on an order. Name and price are copied so old orders never change. */
export const orderItems = pgTable('order_items', {
  id: serial('id').primaryKey(),
  orderId: integer('order_id')
    .notNull()
    .references(() => orders.id, { onDelete: 'cascade' }),
  menuItemId: integer('menu_item_id')
    .notNull()
    .references(() => menuItems.id),
  nameFa: text('name_fa').notNull(),
  unitPriceAfn: integer('unit_price_afn').notNull(),
  quantity: integer('quantity').notNull(),
  note: text('note'),
  lineTotalAfn: integer('line_total_afn').notNull(),
});

export type TranscriptLine = { role: 'user' | 'assistant'; text: string };

/** A log of one call, written by the voice agent when the call ends. */
export const calls = pgTable(
  'calls',
  {
    id: serial('id').primaryKey(),
    sessionId: text('session_id').notNull().unique(),
    channel: text('channel').notNull(),
    callerPhone: text('caller_phone'),
    outcome: text('outcome').notNull(),
    orderId: integer('order_id').references(() => orders.id, { onDelete: 'set null' }),
    startedAt: timestamp('started_at', { withTimezone: true }).notNull(),
    endedAt: timestamp('ended_at', { withTimezone: true }).notNull(),
    durationSec: integer('duration_sec').notNull(),
    transcript: jsonb('transcript').$type<TranscriptLine[]>().notNull().default([]),
    llmPromptTokens: integer('llm_prompt_tokens').notNull().default(0),
    llmCompletionTokens: integer('llm_completion_tokens').notNull().default(0),
    ttsCharacters: integer('tts_characters').notNull().default(0),
    estCostUsd: numeric('est_cost_usd', { precision: 10, scale: 5 }).notNull().default('0'),
    createdAt: timestamp('created_at', { withTimezone: true }).notNull().defaultNow(),
  },
  (t) => [index('calls_created_at_idx').on(t.createdAt)],
);

export type MenuItem = typeof menuItems.$inferSelect;
export type Order = typeof orders.$inferSelect;
export type OrderItem = typeof orderItems.$inferSelect;
export type Call = typeof calls.$inferSelect;

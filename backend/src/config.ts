/**
 * Settings read once from environment variables. Required ones fail fast at
 * startup with a clear message instead of failing later on the first call.
 */
export interface AppConfig {
  port: number;
  databaseUrl: string;
  /** Shared secret the voice agent sends in the `x-agent-key` header. */
  agentApiKey: string;
  /** Token for the staff dashboard and admin endpoints. */
  adminToken: string;
  restaurantName: string;
  deliveryFeeAfn: number;
  etaMinutes: number;
  telegramBotToken: string | null;
  telegramChatId: string | null;
  seedSampleMenu: boolean;
}

export const APP_CONFIG = Symbol('APP_CONFIG');

function required(env: NodeJS.ProcessEnv, name: string): string {
  const value = env[name]?.trim();
  if (!value) {
    throw new Error(`Missing required environment variable ${name}. See .env.example.`);
  }
  return value;
}

function intFrom(env: NodeJS.ProcessEnv, name: string, fallback: number): number {
  const raw = env[name]?.trim();
  if (!raw) return fallback;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${name} must be a whole number, got "${raw}".`);
  }
  return value;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): AppConfig {
  const agentApiKey = required(env, 'AGENT_API_KEY');
  const adminToken = required(env, 'ADMIN_TOKEN');
  for (const [name, value] of [
    ['AGENT_API_KEY', agentApiKey],
    ['ADMIN_TOKEN', adminToken],
  ]) {
    if (value.length < 16) throw new Error(`${name} must be at least 16 characters long.`);
  }
  return {
    port: intFrom(env, 'PORT', 3000),
    databaseUrl: required(env, 'DATABASE_URL'),
    agentApiKey,
    adminToken,
    restaurantName: env.RESTAURANT_NAME?.trim() || 'رستوران نمونه هرات',
    deliveryFeeAfn: intFrom(env, 'DELIVERY_FEE_AFN', 50),
    etaMinutes: intFrom(env, 'ETA_MINUTES', 40),
    telegramBotToken: env.TELEGRAM_BOT_TOKEN?.trim() || null,
    telegramChatId: env.TELEGRAM_CHAT_ID?.trim() || null,
    seedSampleMenu: (env.SEED_SAMPLE_MENU ?? 'true').trim().toLowerCase() !== 'false',
  };
}

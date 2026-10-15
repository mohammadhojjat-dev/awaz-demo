import { loadConfig } from './config.js';

const valid = {
  DATABASE_URL: 'postgres://u:p@localhost/db',
  AGENT_API_KEY: 'agent-key-0123456789',
  ADMIN_TOKEN: 'admin-token-0123456789',
};

describe('loadConfig', () => {
  it('applies defaults', () => {
    const config = loadConfig(valid);
    expect(config).toMatchObject({
      port: 3000,
      deliveryFeeAfn: 50,
      etaMinutes: 40,
      telegramBotToken: null,
      seedSampleMenu: true,
    });
  });

  it('fails fast on missing or weak secrets', () => {
    expect(() => loadConfig({ ...valid, DATABASE_URL: '' })).toThrow(/DATABASE_URL/);
    expect(() => loadConfig({ ...valid, ADMIN_TOKEN: 'short' })).toThrow(/at least 16/);
  });

  it('rejects non-numeric amounts', () => {
    expect(() => loadConfig({ ...valid, DELIVERY_FEE_AFN: 'fifty' })).toThrow(/DELIVERY_FEE_AFN/);
  });

  it('can turn off the sample menu', () => {
    expect(loadConfig({ ...valid, SEED_SAMPLE_MENU: 'false' }).seedSampleMenu).toBe(false);
  });
});

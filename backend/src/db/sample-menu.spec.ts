import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { SAMPLE_MENU } from './sample-menu.js';

// The agent's standalone mode uses its own copy of the sample menu. This keeps
// the two from drifting apart.
describe('sample menu', () => {
  it('matches agent/sample_menu.json', () => {
    const agentMenu = JSON.parse(
      readFileSync(resolve(__dirname, '../../../agent/sample_menu.json'), 'utf-8'),
    ) as Array<Record<string, unknown>>;
    expect(agentMenu.map(({ id: _id, available: _a, sortOrder: _s, ...item }) => item)).toEqual(
      SAMPLE_MENU,
    );
  });

  it('has unique ids and positive prices', () => {
    expect(new Set(SAMPLE_MENU.map((item) => item.slug)).size).toBe(SAMPLE_MENU.length);
    expect(SAMPLE_MENU.every((item) => item.priceAfn > 0)).toBe(true);
  });
});

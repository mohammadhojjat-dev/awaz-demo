import type { MenuItem } from '../db/schema.js';
import { priceOrder, PricingError } from './pricing.js';

const menu: MenuItem[] = [
  { id: 1, slug: 'qabuli-palaw', nameFa: 'قابلی پلو', nameEn: 'Qabuli', category: 'main', priceAfn: 250, aliases: [], available: true, sortOrder: 0 },
  { id: 2, slug: 'doogh', nameFa: 'دوغ', nameEn: 'Doogh', category: 'drink', priceAfn: 50, aliases: [], available: true, sortOrder: 1 },
  { id: 3, slug: 'firni', nameFa: 'فرنی', nameEn: 'Firni', category: 'dessert', priceAfn: 80, aliases: [], available: false, sortOrder: 2 },
];

describe('priceOrder', () => {
  it('prices every line from the menu and adds the delivery fee', () => {
    const result = priceOrder(
      [
        { slug: 'qabuli-palaw', quantity: 2, note: '  بدون کشمش ' },
        { slug: 'doogh', quantity: 3 },
      ],
      menu,
      50,
    );
    expect(result.lines).toEqual([
      expect.objectContaining({ menuItemId: 1, unitPriceAfn: 250, quantity: 2, lineTotalAfn: 500, note: 'بدون کشمش' }),
      expect.objectContaining({ menuItemId: 2, unitPriceAfn: 50, quantity: 3, lineTotalAfn: 150, note: null }),
    ]);
    expect(result.subtotalAfn).toBe(650);
    expect(result.deliveryFeeAfn).toBe(50);
    expect(result.totalAfn).toBe(700);
  });

  it.each([
    [[], 'empty_order'],
    [[{ slug: 'pizza', quantity: 1 }], 'unknown_item'],
    [[{ slug: 'firni', quantity: 1 }], 'unavailable_item'],
    [[{ slug: 'doogh', quantity: 0 }], 'bad_quantity'],
    [[{ slug: 'doogh', quantity: 51 }], 'bad_quantity'],
    [[{ slug: 'doogh', quantity: 1.5 }], 'bad_quantity'],
  ])('rejects %j with %s', (lines, code) => {
    expect(() => priceOrder(lines, menu, 50)).toThrow(PricingError);
    try {
      priceOrder(lines, menu, 50);
    } catch (error) {
      expect((error as PricingError).code).toBe(code);
    }
  });
});

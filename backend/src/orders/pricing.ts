import type { MenuItem } from '../db/schema.js';

export interface RequestedLine {
  slug: string;
  quantity: number;
  note?: string | null;
}

export interface PricedLine {
  menuItemId: number;
  slug: string;
  nameFa: string;
  unitPriceAfn: number;
  quantity: number;
  note: string | null;
  lineTotalAfn: number;
}

export interface PricedOrder {
  lines: PricedLine[];
  subtotalAfn: number;
  deliveryFeeAfn: number;
  totalAfn: number;
}

/** Thrown with a message the agent can act on, e.g. to offer something else. */
export class PricingError extends Error {
  constructor(
    message: string,
    readonly code: 'unknown_item' | 'unavailable_item' | 'bad_quantity' | 'empty_order',
    readonly slug?: string,
  ) {
    super(message);
  }
}

export const MAX_QUANTITY_PER_LINE = 50;

/**
 * Works out every price on the server from the menu. The AI never supplies a
 * price; it only names items and quantities, so a misheard number cannot
 * change what the customer pays.
 */
export function priceOrder(
  requested: RequestedLine[],
  menu: MenuItem[],
  deliveryFeeAfn: number,
): PricedOrder {
  if (requested.length === 0) {
    throw new PricingError('The order has no items.', 'empty_order');
  }
  const bySlug = new Map(menu.map((item) => [item.slug, item]));
  const lines = requested.map((line): PricedLine => {
    const item = bySlug.get(line.slug);
    if (!item) {
      throw new PricingError(`"${line.slug}" is not on the menu.`, 'unknown_item', line.slug);
    }
    if (!item.available) {
      throw new PricingError(`${item.nameFa} is not available today.`, 'unavailable_item', line.slug);
    }
    if (!Number.isInteger(line.quantity) || line.quantity < 1 || line.quantity > MAX_QUANTITY_PER_LINE) {
      throw new PricingError(
        `Quantity for ${item.nameFa} must be between 1 and ${MAX_QUANTITY_PER_LINE}.`,
        'bad_quantity',
        line.slug,
      );
    }
    return {
      menuItemId: item.id,
      slug: item.slug,
      nameFa: item.nameFa,
      unitPriceAfn: item.priceAfn,
      quantity: line.quantity,
      note: line.note?.trim() || null,
      lineTotalAfn: item.priceAfn * line.quantity,
    };
  });
  const subtotalAfn = lines.reduce((sum, line) => sum + line.lineTotalAfn, 0);
  return { lines, subtotalAfn, deliveryFeeAfn, totalAfn: subtotalAfn + deliveryFeeAfn };
}

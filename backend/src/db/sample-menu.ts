/**
 * A sample Herat restaurant menu for the demo. Replace it from the dashboard
 * data or by editing this file before the first start; it is only inserted
 * when the menu table is empty.
 *
 * Prices are invented sample values in afghanis, not real prices.
 * `aliases` are other ways a caller may say the item (spelling and sound
 * variants, English names); they help speech recognition and matching.
 */
export interface SampleMenuItem {
  slug: string;
  nameFa: string;
  nameEn: string;
  category: 'main' | 'side' | 'drink' | 'dessert';
  priceAfn: number;
  aliases: string[];
}

export const SAMPLE_MENU: SampleMenuItem[] = [
  {
    slug: 'qabuli-palaw',
    nameFa: 'قابلی پلو',
    nameEn: 'Qabuli palaw',
    category: 'main',
    priceAfn: 250,
    aliases: ['کابلی پلو', 'قابلی', 'کابلی', 'پلو', 'qabuli', 'kabuli pulao'],
  },
  {
    slug: 'mantu',
    nameFa: 'منتو',
    nameEn: 'Mantu',
    category: 'main',
    priceAfn: 200,
    aliases: ['مانتو', 'منتوی', 'mantu', 'manti'],
  },
  {
    slug: 'ashak',
    nameFa: 'آشک',
    nameEn: 'Ashak',
    category: 'main',
    priceAfn: 200,
    aliases: ['آشک', 'اشک', 'ashak'],
  },
  {
    slug: 'kabab-tikka',
    nameFa: 'کباب تکه',
    nameEn: 'Tikka kebab',
    category: 'main',
    priceAfn: 300,
    aliases: ['کباب تکه', 'تکه', 'tikka kebab', 'tikka'],
  },
  {
    slug: 'kabab-kobide',
    nameFa: 'کباب کوبیده',
    nameEn: 'Kobide kebab',
    category: 'main',
    priceAfn: 250,
    aliases: ['کوبیده', 'کباب کوبیده', 'kobide'],
  },
  {
    slug: 'chalaw-qorma',
    nameFa: 'چلو قورمه',
    nameEn: 'Chalaw with qorma',
    category: 'main',
    priceAfn: 220,
    aliases: ['چلو', 'قورمه', 'چلو قورمه', 'chalaw', 'qorma'],
  },
  {
    slug: 'shorwa',
    nameFa: 'شوربا',
    nameEn: 'Shorwa (soup)',
    category: 'main',
    priceAfn: 150,
    aliases: ['شوربه', 'شوربا', 'shorwa', 'soup'],
  },
  {
    slug: 'bolani',
    nameFa: 'بولانی',
    nameEn: 'Bolani',
    category: 'side',
    priceAfn: 80,
    aliases: ['بولانی', 'بولانی کچالو', 'bolani'],
  },
  {
    slug: 'naan',
    nameFa: 'نان',
    nameEn: 'Naan bread',
    category: 'side',
    priceAfn: 20,
    aliases: ['نان', 'نون', 'naan', 'bread'],
  },
  {
    slug: 'doogh',
    nameFa: 'دوغ',
    nameEn: 'Doogh',
    category: 'drink',
    priceAfn: 50,
    aliases: ['دوغ', 'doogh'],
  },
  {
    slug: 'cola',
    nameFa: 'کوکاکولا',
    nameEn: 'Coca-Cola',
    category: 'drink',
    priceAfn: 40,
    aliases: ['کوکا', 'کولا', 'نوشابه', 'cola', 'coke', 'coca cola'],
  },
  {
    slug: 'green-tea',
    nameFa: 'چای سبز',
    nameEn: 'Green tea',
    category: 'drink',
    priceAfn: 30,
    aliases: ['چای', 'چای سبز', 'green tea', 'tea'],
  },
  {
    slug: 'firni',
    nameFa: 'فرنی',
    nameEn: 'Firni',
    category: 'dessert',
    priceAfn: 80,
    aliases: ['فرنی', 'firni'],
  },
];

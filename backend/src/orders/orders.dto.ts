import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsIn,
  IsInt,
  IsOptional,
  IsString,
  Length,
  Max,
  MaxLength,
  Min,
  ValidateNested,
} from 'class-validator';
import { MAX_QUANTITY_PER_LINE } from './pricing.js';

export const CHANNELS = ['web', 'whatsapp', 'phone', 'eval'] as const;
export const ORDER_STATUSES = ['new', 'callback', 'accepted', 'delivered', 'cancelled'] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export class OrderLineDto {
  @IsString()
  @Length(1, 80)
  slug: string;

  @IsInt()
  @Min(1)
  @Max(MAX_QUANTITY_PER_LINE)
  quantity: number;

  @IsOptional()
  @IsString()
  @MaxLength(200)
  note?: string;
}

export class QuoteDto {
  @IsArray()
  @ArrayMaxSize(30)
  @ValidateNested({ each: true })
  @Type(() => OrderLineDto)
  items: OrderLineDto[];
}

/**
 * What the voice agent sends. `status: 'new'` is a confirmed order;
 * `status: 'callback'` asks staff to phone the customer back.
 */
export class CreateOrderDto {
  @IsString()
  @Length(1, 120)
  sessionId: string;

  @IsIn(CHANNELS)
  channel: (typeof CHANNELS)[number];

  @IsIn(['new', 'callback'])
  status: 'new' | 'callback';

  @IsArray()
  @ArrayMaxSize(30)
  @ValidateNested({ each: true })
  @Type(() => OrderLineDto)
  items: OrderLineDto[];

  @IsOptional()
  @IsString()
  @MaxLength(120)
  customerName?: string;

  @IsOptional()
  @IsString()
  @MaxLength(40)
  customerPhone?: string;

  @IsOptional()
  @IsString()
  @MaxLength(300)
  address?: string;

  @IsOptional()
  @IsString()
  @MaxLength(200)
  landmark?: string;

  @IsOptional()
  @IsString()
  @MaxLength(500)
  notes?: string;

  @IsOptional()
  @IsString()
  @MaxLength(300)
  callbackReason?: string;
}

export class UpdateStatusDto {
  @IsIn(ORDER_STATUSES)
  status: OrderStatus;
}

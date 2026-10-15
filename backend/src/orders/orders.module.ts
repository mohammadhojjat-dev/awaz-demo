import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpCode,
  Inject,
  Injectable,
  Logger,
  Module,
  NotFoundException,
  Param,
  ParseIntPipe,
  Patch,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { and, desc, eq, inArray } from 'drizzle-orm';
import { AdminGuard, AgentKeyGuard, AgentOrAdminGuard } from '../auth/guards.js';
import { APP_CONFIG, type AppConfig } from '../config.js';
import { DB, type Database } from '../db/database.module.js';
import { orderItems, orders, type Order, type OrderItem } from '../db/schema.js';
import { MenuModule, MenuService } from '../menu/menu.module.js';
import { TelegramService } from '../notify/telegram.service.js';
import { CreateOrderDto, QuoteDto, UpdateStatusDto } from './orders.dto.js';
import { priceOrder, PricingError, type PricedOrder } from './pricing.js';

export type OrderWithItems = Order & { items: OrderItem[] };

export interface CreatedOrder {
  order: OrderWithItems;
  /** False when this session already had an order and it was returned again. */
  created: boolean;
  telegramSent: boolean;
}

@Injectable()
export class OrdersService {
  private readonly logger = new Logger(OrdersService.name);

  constructor(
    @Inject(DB) private readonly db: Database,
    @Inject(APP_CONFIG) private readonly config: AppConfig,
    private readonly menu: MenuService,
    private readonly telegram: TelegramService,
  ) {}

  /** Prices a cart without saving it, so the agent can read back the exact total. */
  async quote(dto: QuoteDto): Promise<PricedOrder> {
    const menu = await this.menu.list();
    try {
      return priceOrder(dto.items, menu, this.config.deliveryFeeAfn);
    } catch (error) {
      if (error instanceof PricingError) {
        throw new BadRequestException({ message: error.message, code: error.code, slug: error.slug });
      }
      throw error;
    }
  }

  /**
   * Saves a confirmed order or a callback request and alerts staff.
   * Calling it twice for one call session returns the first order instead of
   * creating a duplicate, so a retried request is safe.
   */
  async create(dto: CreateOrderDto): Promise<CreatedOrder> {
    const existing = await this.db.query.orders.findFirst({
      where: and(eq(orders.sessionId, dto.sessionId), eq(orders.status, dto.status)),
    });
    if (existing) {
      return { order: await this.withItems(existing), created: false, telegramSent: false };
    }

    if (dto.status === 'new') {
      if (!dto.customerName?.trim()) throw new BadRequestException('customerName is required');
      if (!dto.address?.trim()) throw new BadRequestException('address is required');
    } else if (!dto.callbackReason?.trim()) {
      throw new BadRequestException('callbackReason is required for a callback');
    }

    let priced: PricedOrder;
    if (dto.items.length === 0 && dto.status === 'callback') {
      priced = { lines: [], subtotalAfn: 0, deliveryFeeAfn: 0, totalAfn: 0 };
    } else {
      priced = await this.quote({ items: dto.items });
    }

    let saved: OrderWithItems;
    try {
      saved = await this.insertOrder(dto, priced);
    } catch (error) {
      // Two requests for the same session raced; the other one won.
      if ((error as { code?: string }).code === '23505') {
        const winner = await this.db.query.orders.findFirst({
          where: and(eq(orders.sessionId, dto.sessionId), eq(orders.status, dto.status)),
        });
        if (winner) return { order: await this.withItems(winner), created: false, telegramSent: false };
      }
      throw error;
    }

    this.logger.log(`Saved ${saved.status} order #${saved.code} (${saved.totalAfn} AFN)`);
    const telegramSent = await this.telegram.notifyOrder(saved, saved.items);
    return { order: saved, created: true, telegramSent };
  }

  private insertOrder(dto: CreateOrderDto, priced: PricedOrder): Promise<OrderWithItems> {
    return this.db.transaction(async (tx) => {
      const [inserted] = await tx
        .insert(orders)
        .values({
          code: `pending-${dto.sessionId}-${dto.status}`,
          sessionId: dto.sessionId,
          channel: dto.channel,
          status: dto.status,
          customerName: dto.customerName?.trim() || null,
          customerPhone: dto.customerPhone?.trim() || null,
          address: dto.address?.trim() || null,
          landmark: dto.landmark?.trim() || null,
          notes: dto.notes?.trim() || null,
          callbackReason: dto.callbackReason?.trim() || null,
          subtotalAfn: priced.subtotalAfn,
          deliveryFeeAfn: priced.deliveryFeeAfn,
          totalAfn: priced.totalAfn,
          etaMinutes: dto.status === 'new' ? this.config.etaMinutes : null,
        })
        .returning();
      const [order] = await tx
        .update(orders)
        .set({ code: String(1000 + inserted.id) })
        .where(eq(orders.id, inserted.id))
        .returning();
      const items =
        priced.lines.length === 0
          ? []
          : await tx
              .insert(orderItems)
              .values(
                priced.lines.map((line) => ({
                  orderId: order.id,
                  menuItemId: line.menuItemId,
                  nameFa: line.nameFa,
                  unitPriceAfn: line.unitPriceAfn,
                  quantity: line.quantity,
                  note: line.note,
                  lineTotalAfn: line.lineTotalAfn,
                })),
              )
              .returning();
      return { ...order, items };
    });
  }

  async list(limit: number): Promise<OrderWithItems[]> {
    const rows = await this.db.select().from(orders).orderBy(desc(orders.createdAt)).limit(limit);
    if (rows.length === 0) return [];
    const items = await this.db
      .select()
      .from(orderItems)
      .where(inArray(orderItems.orderId, rows.map((row) => row.id)));
    return rows.map((row) => ({ ...row, items: items.filter((item) => item.orderId === row.id) }));
  }

  async get(id: number): Promise<OrderWithItems> {
    const row = await this.db.query.orders.findFirst({ where: eq(orders.id, id) });
    if (!row) throw new NotFoundException(`Order ${id} not found`);
    return this.withItems(row);
  }

  async setStatus(id: number, dto: UpdateStatusDto): Promise<OrderWithItems> {
    const [row] = await this.db
      .update(orders)
      .set({ status: dto.status, updatedAt: new Date() })
      .where(eq(orders.id, id))
      .returning();
    if (!row) throw new NotFoundException(`Order ${id} not found`);
    return this.withItems(row);
  }

  private async withItems(order: Order): Promise<OrderWithItems> {
    const items = await this.db.select().from(orderItems).where(eq(orderItems.orderId, order.id));
    return { ...order, items };
  }
}

@Controller('orders')
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  /** Exact prices for a cart, without saving. Used by the agent before read-back. */
  @Post('quote')
  @HttpCode(200)
  @UseGuards(AgentOrAdminGuard)
  quote(@Body() body: QuoteDto): Promise<PricedOrder> {
    return this.orders.quote(body);
  }

  @Post()
  @UseGuards(AgentKeyGuard)
  async create(@Body() body: CreateOrderDto) {
    const result = await this.orders.create(body);
    const { order } = result;
    return {
      id: order.id,
      code: order.code,
      status: order.status,
      totalAfn: order.totalAfn,
      etaMinutes: order.etaMinutes,
      created: result.created,
      telegramSent: result.telegramSent,
    };
  }

  @Get()
  @UseGuards(AdminGuard)
  list(@Query('limit') limit?: string): Promise<OrderWithItems[]> {
    const parsed = Number(limit ?? 50);
    return this.orders.list(Number.isInteger(parsed) && parsed > 0 && parsed <= 200 ? parsed : 50);
  }

  @Get(':id')
  @UseGuards(AdminGuard)
  get(@Param('id', ParseIntPipe) id: number): Promise<OrderWithItems> {
    return this.orders.get(id);
  }

  @Patch(':id/status')
  @UseGuards(AdminGuard)
  setStatus(
    @Param('id', ParseIntPipe) id: number,
    @Body() body: UpdateStatusDto,
  ): Promise<OrderWithItems> {
    return this.orders.setStatus(id, body);
  }
}

@Module({
  imports: [MenuModule],
  controllers: [OrdersController],
  providers: [OrdersService, TelegramService],
  exports: [OrdersService],
})
export class OrdersModule {}

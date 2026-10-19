import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Inject,
  Injectable,
  Module,
  NotFoundException,
  Param,
  ParseIntPipe,
  Patch,
  UseGuards,
} from '@nestjs/common';
import { IsBoolean, IsInt, IsOptional, Max, Min } from 'class-validator';
import { asc, eq } from 'drizzle-orm';
import { AdminGuard, AgentOrAdminGuard } from '../auth/guards.js';
import { DB, type Database } from '../db/database.module.js';
import { menuItems, type MenuItem } from '../db/schema.js';

export class UpdateMenuItemDto {
  @IsOptional()
  @IsBoolean()
  available?: boolean;

  @IsOptional()
  @IsInt()
  @Min(1)
  @Max(100000)
  priceAfn?: number;
}

@Injectable()
export class MenuService {
  constructor(@Inject(DB) private readonly db: Database) {}

  list(onlyAvailable = false): Promise<MenuItem[]> {
    const query = this.db.select().from(menuItems).orderBy(asc(menuItems.sortOrder), asc(menuItems.id));
    return onlyAvailable ? query.where(eq(menuItems.available, true)) : query;
  }

  async update(id: number, changes: UpdateMenuItemDto): Promise<MenuItem> {
    // Drizzle throws "No values to set" on an empty update, which would surface as a 500.
    if (changes.available === undefined && changes.priceAfn === undefined) {
      throw new BadRequestException('Send at least one of: available, priceAfn');
    }
    const [row] = await this.db.update(menuItems).set(changes).where(eq(menuItems.id, id)).returning();
    if (!row) throw new NotFoundException(`Menu item ${id} not found`);
    return row;
  }
}

@Controller('menu')
export class MenuController {
  constructor(private readonly menu: MenuService) {}

  /** The full menu, including items marked unavailable (they carry `available: false`). */
  @Get()
  @UseGuards(AgentOrAdminGuard)
  list(): Promise<MenuItem[]> {
    return this.menu.list();
  }

  /** Staff can mark an item sold out or change its price. */
  @Patch(':id')
  @UseGuards(AdminGuard)
  update(@Param('id', ParseIntPipe) id: number, @Body() body: UpdateMenuItemDto): Promise<MenuItem> {
    return this.menu.update(id, body);
  }
}

@Module({
  controllers: [MenuController],
  providers: [MenuService],
  exports: [MenuService],
})
export class MenuModule {}

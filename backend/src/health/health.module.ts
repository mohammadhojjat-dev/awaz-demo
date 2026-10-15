import { Controller, Get, Inject, Module, Res, ServiceUnavailableException } from '@nestjs/common';
import { sql } from 'drizzle-orm';
import type { Response } from 'express';
import { resolve } from 'node:path';
import { DB, type Database } from '../db/database.module.js';

@Controller()
export class HealthController {
  constructor(@Inject(DB) private readonly db: Database) {}

  @Get('health')
  async health() {
    try {
      await this.db.execute(sql`select 1`);
      return { ok: true, database: true };
    } catch {
      throw new ServiceUnavailableException({ ok: false, database: false });
    }
  }

  /**
   * The staff dashboard page. The page itself holds no data: it asks for the
   * admin token and then reads orders, calls and stats from the API.
   */
  @Get('dashboard')
  dashboard(@Res() res: Response) {
    const publicDir = process.env.PUBLIC_DIR ?? resolve(process.cwd(), 'public');
    res.sendFile(resolve(publicDir, 'dashboard.html'));
  }
}

@Module({ controllers: [HealthController] })
export class HealthModule {}

import {
  Global,
  Inject,
  Logger,
  Module,
  OnApplicationShutdown,
  OnModuleInit,
} from '@nestjs/common';
import { sql } from 'drizzle-orm';
import { drizzle, NodePgDatabase } from 'drizzle-orm/node-postgres';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import { resolve } from 'node:path';
import pg from 'pg';
import type { Pool } from 'pg';
import { APP_CONFIG, type AppConfig } from '../config.js';
import { SAMPLE_MENU } from './sample-menu.js';
import * as schema from './schema.js';

export type Database = NodePgDatabase<typeof schema>;
export const DB = Symbol('DB');
export const PG_POOL = Symbol('PG_POOL');

@Global()
@Module({
  providers: [
    {
      provide: PG_POOL,
      inject: [APP_CONFIG],
      useFactory: (config: AppConfig) =>
        new pg.Pool({ connectionString: config.databaseUrl, max: 10 }),
    },
    {
      provide: DB,
      inject: [PG_POOL],
      useFactory: (pool: Pool): Database => drizzle(pool, { schema }),
    },
  ],
  exports: [DB, PG_POOL],
})
export class DatabaseModule implements OnModuleInit, OnApplicationShutdown {
  private readonly logger = new Logger(DatabaseModule.name);

  constructor(
    @Inject(DB) private readonly db: Database,
    @Inject(PG_POOL) private readonly pool: Pool,
    @Inject(APP_CONFIG) private readonly config: AppConfig,
  ) {}

  /** Bring the schema up to date, then add the sample menu if it is empty. */
  async onModuleInit(): Promise<void> {
    const migrationsFolder = process.env.MIGRATIONS_DIR ?? resolve(process.cwd(), 'drizzle');
    await migrate(this.db, { migrationsFolder });
    this.logger.log('Database migrations are up to date');

    if (!this.config.seedSampleMenu) return;
    const [{ count }] = await this.db
      .select({ count: sql<number>`count(*)::int` })
      .from(schema.menuItems);
    if (count > 0) return;
    await this.db.insert(schema.menuItems).values(
      SAMPLE_MENU.map((item, index) => ({ ...item, sortOrder: index })),
    );
    this.logger.log(`Inserted the sample menu (${SAMPLE_MENU.length} items)`);
  }

  async onApplicationShutdown(): Promise<void> {
    await this.pool.end();
  }
}

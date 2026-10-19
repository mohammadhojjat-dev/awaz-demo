import { Global, Module } from '@nestjs/common';
import { CallsModule } from './calls/calls.module.js';
import { APP_CONFIG, loadConfig } from './config.js';
import { DatabaseModule } from './db/database.module.js';
import { HealthModule } from './health/health.module.js';
import { MenuModule } from './menu/menu.module.js';
import { OrdersModule } from './orders/orders.module.js';

@Global()
@Module({
  providers: [{ provide: APP_CONFIG, useFactory: () => loadConfig() }],
  exports: [APP_CONFIG],
})
export class ConfigModule {}

@Module({
  imports: [ConfigModule, DatabaseModule, MenuModule, OrdersModule, CallsModule, HealthModule],
})
export class AppModule {}

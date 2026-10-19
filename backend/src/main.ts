import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module.js';
import { configureApp } from './app.setup.js';
import { loadConfig } from './config.js';

async function bootstrap() {
  const config = loadConfig();
  const app = await NestFactory.create(AppModule);
  configureApp(app);
  await app.listen(config.port, process.env.HOST ?? '0.0.0.0');
}

await bootstrap();

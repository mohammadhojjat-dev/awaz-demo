import { INestApplication, ValidationPipe } from '@nestjs/common';

/** Applies the request validation used in production and in e2e tests. */
export function configureApp(app: INestApplication): void {
  app.useGlobalPipes(
    new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }),
  );
  app.enableShutdownHooks();
}

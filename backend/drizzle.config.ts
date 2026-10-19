import { defineConfig } from 'drizzle-kit';

// Used by `npm run db:generate` to turn changes in src/db/schema.ts into a new
// SQL migration in ./drizzle. The app applies pending migrations at startup.
export default defineConfig({
  dialect: 'postgresql',
  schema: './src/db/schema.ts',
  out: './drizzle',
  dbCredentials: { url: process.env.DATABASE_URL ?? '' },
});

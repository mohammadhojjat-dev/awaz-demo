import {
  CanActivate,
  ExecutionContext,
  Inject,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import type { Request } from 'express';
import { timingSafeEqual } from 'node:crypto';
import { APP_CONFIG, type AppConfig } from '../config.js';

/** Compares secrets in constant time so response timing leaks nothing. */
export function secretsMatch(given: string | undefined, expected: string): boolean {
  if (!given) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  return a.length === b.length && timingSafeEqual(a, b);
}

function bearer(request: Request): string | undefined {
  const header = request.headers.authorization;
  if (!header?.startsWith('Bearer ')) return undefined;
  return header.slice('Bearer '.length).trim();
}

/** Lets in only the voice agent, which sends the shared `x-agent-key`. */
@Injectable()
export class AgentKeyGuard implements CanActivate {
  constructor(@Inject(APP_CONFIG) private readonly config: AppConfig) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();
    const key = request.headers['x-agent-key'];
    if (secretsMatch(typeof key === 'string' ? key : undefined, this.config.agentApiKey)) {
      return true;
    }
    throw new UnauthorizedException('Invalid agent key');
  }
}

/** Lets in staff only: `Authorization: Bearer <ADMIN_TOKEN>`. */
@Injectable()
export class AdminGuard implements CanActivate {
  constructor(@Inject(APP_CONFIG) private readonly config: AppConfig) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();
    if (secretsMatch(bearer(request), this.config.adminToken)) return true;
    throw new UnauthorizedException('Invalid admin token');
  }
}

/** For endpoints both the agent and staff may read, such as the menu. */
@Injectable()
export class AgentOrAdminGuard implements CanActivate {
  constructor(@Inject(APP_CONFIG) private readonly config: AppConfig) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest<Request>();
    const key = request.headers['x-agent-key'];
    if (secretsMatch(typeof key === 'string' ? key : undefined, this.config.agentApiKey)) {
      return true;
    }
    if (secretsMatch(bearer(request), this.config.adminToken)) return true;
    throw new UnauthorizedException('Invalid credentials');
  }
}

import {
  Body,
  Controller,
  Get,
  Inject,
  Injectable,
  Module,
  Post,
  Query,
  UseGuards,
} from '@nestjs/common';
import { Type } from 'class-transformer';
import {
  ArrayMaxSize,
  IsArray,
  IsDateString,
  IsIn,
  IsInt,
  IsNumber,
  IsOptional,
  IsString,
  Length,
  MaxLength,
  Min,
  ValidateNested,
} from 'class-validator';
import { desc, sql } from 'drizzle-orm';
import { AdminGuard, AgentKeyGuard } from '../auth/guards.js';
import { DB, type Database } from '../db/database.module.js';
import { calls, type Call } from '../db/schema.js';
import { CHANNELS } from '../orders/orders.dto.js';

export const CALL_OUTCOMES = ['ordered', 'callback', 'abandoned'] as const;

export class TranscriptLineDto {
  @IsIn(['user', 'assistant'])
  role: 'user' | 'assistant';

  @IsString()
  @MaxLength(4000)
  text: string;
}

export class CreateCallDto {
  @IsString()
  @Length(1, 120)
  sessionId: string;

  @IsIn(CHANNELS)
  channel: (typeof CHANNELS)[number];

  @IsOptional()
  @IsString()
  @MaxLength(40)
  callerPhone?: string;

  @IsIn(CALL_OUTCOMES)
  outcome: (typeof CALL_OUTCOMES)[number];

  @IsOptional()
  @IsInt()
  orderId?: number;

  @IsDateString()
  startedAt: string;

  @IsDateString()
  endedAt: string;

  @IsArray()
  @ArrayMaxSize(400)
  @ValidateNested({ each: true })
  @Type(() => TranscriptLineDto)
  transcript: TranscriptLineDto[];

  @IsInt()
  @Min(0)
  llmPromptTokens: number;

  @IsInt()
  @Min(0)
  llmCompletionTokens: number;

  @IsInt()
  @Min(0)
  ttsCharacters: number;

  @IsNumber()
  @Min(0)
  estCostUsd: number;
}

export interface CallStats {
  calls: number;
  ordered: number;
  callbacks: number;
  abandoned: number;
  /** Share of calls the agent finished alone with a confirmed order, 0..1. */
  completionRate: number;
  avgDurationSec: number;
  avgCostUsd: number;
  totalCostUsd: number;
}

@Injectable()
export class CallsService {
  constructor(@Inject(DB) private readonly db: Database) {}

  /** Saves the call log; a second report for the same session replaces the first. */
  async record(dto: CreateCallDto): Promise<Call> {
    const startedAt = new Date(dto.startedAt);
    const endedAt = new Date(dto.endedAt);
    const values = {
      sessionId: dto.sessionId,
      channel: dto.channel,
      callerPhone: dto.callerPhone ?? null,
      outcome: dto.outcome,
      orderId: dto.orderId ?? null,
      startedAt,
      endedAt,
      durationSec: Math.max(0, Math.round((endedAt.getTime() - startedAt.getTime()) / 1000)),
      transcript: dto.transcript,
      llmPromptTokens: dto.llmPromptTokens,
      llmCompletionTokens: dto.llmCompletionTokens,
      ttsCharacters: dto.ttsCharacters,
      estCostUsd: dto.estCostUsd.toFixed(5),
    };
    const [row] = await this.db
      .insert(calls)
      .values(values)
      .onConflictDoUpdate({ target: calls.sessionId, set: values })
      .returning();
    return row;
  }

  list(limit: number): Promise<Call[]> {
    return this.db.select().from(calls).orderBy(desc(calls.createdAt)).limit(limit);
  }

  async stats(): Promise<CallStats> {
    const [row] = await this.db
      .select({
        calls: sql<number>`count(*)::int`,
        ordered: sql<number>`count(*) filter (where ${calls.outcome} = 'ordered')::int`,
        callbacks: sql<number>`count(*) filter (where ${calls.outcome} = 'callback')::int`,
        abandoned: sql<number>`count(*) filter (where ${calls.outcome} = 'abandoned')::int`,
        avgDurationSec: sql<number>`coalesce(avg(${calls.durationSec}), 0)::float`,
        avgCostUsd: sql<number>`coalesce(avg(${calls.estCostUsd}), 0)::float`,
        totalCostUsd: sql<number>`coalesce(sum(${calls.estCostUsd}), 0)::float`,
      })
      .from(calls);
    return {
      ...row,
      completionRate: row.calls === 0 ? 0 : row.ordered / row.calls,
    };
  }
}

@Controller()
export class CallsController {
  constructor(private readonly calls: CallsService) {}

  @Post('calls')
  @UseGuards(AgentKeyGuard)
  async record(@Body() body: CreateCallDto) {
    const row = await this.calls.record(body);
    return { id: row.id };
  }

  @Get('calls')
  @UseGuards(AdminGuard)
  list(@Query('limit') limit?: string): Promise<Call[]> {
    const parsed = Number(limit ?? 50);
    return this.calls.list(Number.isInteger(parsed) && parsed > 0 && parsed <= 200 ? parsed : 50);
  }

  /** The numbers to show investors: completion rate, duration, cost per call. */
  @Get('stats')
  @UseGuards(AdminGuard)
  stats(): Promise<CallStats> {
    return this.calls.stats();
  }
}

@Module({
  controllers: [CallsController],
  providers: [CallsService],
})
export class CallsModule {}

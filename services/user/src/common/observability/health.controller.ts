import { Controller, Get, Res, ServiceUnavailableException } from '@nestjs/common';
import { PrismaService } from '../../prisma/prisma.service';
import { RedisService } from '../../redis/redis.service';
import { MetricsService } from './metrics.service';
import { Response } from 'express';

@Controller()
export class HealthController {
  constructor(
    private readonly prisma: PrismaService,
    private readonly redis: RedisService,
    private readonly metricsService: MetricsService,
  ) {}

  /**
   * GET /health
   * Liveness Check: Xác nhận tiến trình ứng dụng đang chạy bình thường.
   */
  @Get('health')
  getLiveness() {
    return {
      status: 'ok',
      uptime: process.uptime(),
    };
  }

  /**
   * GET /ready
   * Readiness Check: Xác thực khả năng kết nối tới các hệ thống phụ thuộc là Database và Redis.
   */
  @Get('ready')
  async getReadiness() {
    let dbStatus = 'down';
    let redisStatus = 'down';
    const errors: string[] = [];

    // 1. Kiểm tra Database
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      dbStatus = 'up';
    } catch (e: any) {
      errors.push(`Database connection failed: ${e.message}`);
    }

    // 2. Kiểm tra Redis
    try {
      const ping = await this.redis.getClient().ping();
      if (ping === 'PONG') {
        redisStatus = 'up';
      } else {
        errors.push(`Redis ping response: ${ping}`);
      }
    } catch (e: any) {
      errors.push(`Redis connection failed: ${e.message}`);
    }

    const dependencies = {
      database: dbStatus,
      redis: redisStatus,
    };

    if (errors.length > 0) {
      throw new ServiceUnavailableException({
        status: 'error',
        dependencies,
        reasons: errors,
      });
    }

    return {
      status: 'ready',
      dependencies,
    };
  }

  /**
   * GET /metrics
   * Trả về danh sách metrics theo định dạng chuẩn Prometheus.
   */
  @Get('metrics')
  getMetrics(@Res() res: any) {
    res.set('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
    res.send(this.metricsService.getMetricsResponse());
  }
}

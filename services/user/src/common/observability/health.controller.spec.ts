import { Test, TestingModule } from '@nestjs/testing';
import { HealthController } from './health.controller';
import { PrismaService } from '../../prisma/prisma.service';
import { RedisService } from '../../redis/redis.service';
import { MetricsService } from './metrics.service';
import { ServiceUnavailableException } from '@nestjs/common';

describe('HealthController', () => {
  let controller: HealthController;
  let prisma: any;
  let redis: any;
  let metricsService: MetricsService;

  const mockPrisma = {
    $queryRaw: jest.fn(),
  };

  const mockRedisClient = {
    ping: jest.fn(),
  };

  const mockRedis = {
    getClient: jest.fn(() => mockRedisClient),
  };

  const mockMetricsService = {
    getMetricsResponse: jest.fn(() => Promise.resolve('mock-metrics')),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      controllers: [HealthController],
      providers: [
        { provide: PrismaService, useValue: mockPrisma },
        { provide: RedisService, useValue: mockRedis },
        { provide: MetricsService, useValue: mockMetricsService },
      ],
    }).compile();

    controller = module.get<HealthController>(HealthController);
    prisma = module.get<PrismaService>(PrismaService);
    redis = module.get<RedisService>(RedisService);
    metricsService = module.get<MetricsService>(MetricsService);
  });

  it('should be defined', () => {
    expect(controller).toBeDefined();
  });

  describe('GET /health', () => {
    it('should return liveness status', () => {
      const result = controller.getLiveness();
      expect(result).toHaveProperty('status', 'ok');
      expect(result).toHaveProperty('uptime');
    });
  });

  describe('GET /ready', () => {
    it('should return status ready if db and redis are up', async () => {
      mockPrisma.$queryRaw.mockResolvedValue([1]);
      mockRedis.getClient().ping.mockResolvedValue('PONG');

      const result = await controller.getReadiness();
      expect(result).toEqual({
        status: 'ready',
        dependencies: {
          database: 'up',
          redis: 'up',
        },
      });
    });

    it('should throw ServiceUnavailableException if database is down', async () => {
      mockPrisma.$queryRaw.mockRejectedValue(new Error('DB connection refused'));
      mockRedis.getClient().ping.mockResolvedValue('PONG');

      await expect(controller.getReadiness()).rejects.toThrow(ServiceUnavailableException);
    });

    it('should throw ServiceUnavailableException if redis is down', async () => {
      mockPrisma.$queryRaw.mockResolvedValue([1]);
      mockRedis.getClient().ping.mockRejectedValue(new Error('Redis connection timeout'));

      await expect(controller.getReadiness()).rejects.toThrow(ServiceUnavailableException);
    });
  });

  describe('GET /metrics', () => {
    it('should return metrics list', async () => {
      const mockRes = {
        set: jest.fn(),
        send: jest.fn(),
      } as any;

      await controller.getMetrics(mockRes);

      expect(mockRes.set).toHaveBeenCalledWith('Content-Type', 'text/plain; version=0.0.4; charset=utf-8');
      expect(mockRes.send).toHaveBeenCalledWith('mock-metrics');
    });
  });
});

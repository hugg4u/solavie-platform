import { Test, TestingModule } from '@nestjs/testing';
import { ServiceRegistryClient } from './service-registry.client';
import { RedisService } from '../../redis/redis.service';

describe('ServiceRegistryClient', () => {
  let client: ServiceRegistryClient;
  let redisService: any;
  let mockRedisClient: any;

  beforeEach(async () => {
    mockRedisClient = {
      sAdd: jest.fn().mockResolvedValue(1),
      setEx: jest.fn().mockResolvedValue('OK'),
      sRem: jest.fn().mockResolvedValue(1),
      del: jest.fn().mockResolvedValue(1),
    };

    const mockRedis = {
      getClient: jest.fn(() => mockRedisClient),
    };

    const module: TestingModule = await Test.createTestingModule({
      providers: [
        ServiceRegistryClient,
        { provide: RedisService, useValue: mockRedis },
      ],
    }).compile();

    client = module.get<ServiceRegistryClient>(ServiceRegistryClient);
    redisService = module.get<RedisService>(RedisService);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should be defined', () => {
    expect(client).toBeDefined();
  });

  describe('Lifecycle Hooks & Heartbeat', () => {
    it('should register service node on application bootstrap and start heartbeat', async () => {
      jest.useFakeTimers();

      // Giả lập hàm getInternalIp trả về IP cố định để kiểm tra
      (client as any).getInternalIp = jest.fn().mockResolvedValue('172.20.0.10');

      await client.onApplicationBootstrap();

      // Xác thực đăng ký ban đầu
      expect(mockRedisClient.sAdd).toHaveBeenCalledWith('registry:service:user', '172.20.0.10:3008');
      expect(mockRedisClient.setEx).toHaveBeenCalledWith('registry:service:user:node:172.20.0.10:3008', 15, 'alive');

      // Reset mock counts để kiểm tra heartbeat
      mockRedisClient.sAdd.mockClear();
      mockRedisClient.setEx.mockClear();

      // Cho chạy qua 5 giây (1 chu kỳ heartbeat) và tự động giải quyết các async microtasks
      await jest.advanceTimersByTimeAsync(5000);

      expect(mockRedisClient.setEx).toHaveBeenCalledWith('registry:service:user:node:172.20.0.10:3008', 15, 'alive');
      expect(mockRedisClient.sAdd).toHaveBeenCalledWith('registry:service:user', '172.20.0.10:3008');

      // Shutdown để hủy đăng ký
      await client.beforeApplicationShutdown();
      expect(mockRedisClient.sRem).toHaveBeenCalledWith('registry:service:user', '172.20.0.10:3008');
      expect(mockRedisClient.del).toHaveBeenCalledWith('registry:service:user:node:172.20.0.10:3008');
    });
  });
});

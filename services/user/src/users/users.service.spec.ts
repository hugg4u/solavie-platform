import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { PrismaService } from '../prisma/prisma.service';
import { KeycloakAdminService } from '../keycloak/keycloak-admin.service';
import { RedisService } from '../redis/redis.service';
import { HttpService } from '@nestjs/axios';
import { of } from 'rxjs';

describe('UsersService', () => {
  let service: UsersService;
  let prisma: PrismaService;
  let keycloakAdmin: KeycloakAdminService;
  let redis: RedisService;
  let http: HttpService;

  const mockPrisma = {
    runInTenantContext: jest.fn((cb) => cb(mockPrisma)),
    user: {
      findUnique: jest.fn(),
      create: jest.fn(),
      update: jest.fn(),
      updateMany: jest.fn(),
      upsert: jest.fn(),
    },
    userPreference: {
      findUnique: jest.fn(),
      update: jest.fn(),
    },
  };

  const mockKeycloakAdmin = {
    createUser: jest.fn(),
    updateUser: jest.fn(),
    suspendUser: jest.fn(),
  };

  const mockRedis = {
    setEx: jest.fn(),
    publish: jest.fn(),
    getClient: jest.fn(() => ({
      del: jest.fn(),
    })),
  };

  const mockHttp = {
    get: jest.fn(),
    post: jest.fn(),
    put: jest.fn(),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        { provide: PrismaService, useValue: mockPrisma },
        { provide: KeycloakAdminService, useValue: mockKeycloakAdmin },
        { provide: RedisService, useValue: mockRedis },
        { provide: HttpService, useValue: mockHttp },
      ],
    }).compile();

    service = module.get<UsersService>(UsersService);
    prisma = module.get<PrismaService>(PrismaService);
    keycloakAdmin = module.get<KeycloakAdminService>(KeycloakAdminService);
    redis = module.get<RedisService>(RedisService);
    http = module.get<HttpService>(HttpService);
    
    // Default mocks
    mockHttp.post.mockReturnValue(of({ data: { access_token: 'admin-token' } }));
  });

  it('should be defined', () => {
    expect(service).toBeDefined();
  });

  describe('getMe', () => {
    it('should return user profile if user exists and is ACTIVE', async () => {
      const mockUser = {
        id: 'user-123',
        tenantId: 'tenant-123',
        phoneNumber: '0987654321',
        avatarUrl: 'http://avatar',
        department: 'IT',
        status: 'ACTIVE',
        createdAt: new Date(),
        updatedAt: new Date(),
        preferences: { theme: 'dark', language: 'vi' },
      };

      mockPrisma.user.findUnique.mockResolvedValue(mockUser);
      mockHttp.get.mockReturnValue(of({ data: { email: 'test@email.com', firstName: 'John', lastName: 'Doe' } }));

      const result = await service.getMe('user-123', 'tenant-123');

      expect(result).toBeDefined();
      expect(result.id).toBe('user-123');
      expect(result.status).toBe('ACTIVE');
      expect(result.email).toBe('test@email.com');
      expect(result.firstName).toBe('John');
      expect(result.lastName).toBe('Doe');
    });
  });
});

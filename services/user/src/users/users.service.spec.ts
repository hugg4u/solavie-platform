import { Test, TestingModule } from '@nestjs/testing';
import { UsersService } from './users.service';
import { PrismaService } from '../prisma/prisma.service';
import { KeycloakAdminService } from '../keycloak/keycloak-admin.service';
import { RedisService } from '../redis/redis.service';
import { HttpService } from '@nestjs/axios';
import { of } from 'rxjs';
import { NotFoundException, ConflictException, ForbiddenException } from '@nestjs/common';
import { UserErrorCode, UserSuccessCode } from '../common/constants/user-codes';

describe('UsersService', () => {
  let service: UsersService;
  let prisma: any;
  let keycloakAdmin: any;
  let redis: any;
  let http: any;

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

  const mockKafka = {
    emit: jest.fn(),
    connect: jest.fn().mockResolvedValue(null),
  };

  beforeEach(async () => {
    const module: TestingModule = await Test.createTestingModule({
      providers: [
        UsersService,
        { provide: PrismaService, useValue: mockPrisma },
        { provide: KeycloakAdminService, useValue: mockKeycloakAdmin },
        { provide: RedisService, useValue: mockRedis },
        { provide: HttpService, useValue: mockHttp },
        { provide: 'KAFKA_SERVICE', useValue: mockKafka },
      ],
    }).compile();

    service = module.get<UsersService>(UsersService);
    prisma = module.get<PrismaService>(PrismaService);
    keycloakAdmin = module.get<KeycloakAdminService>(KeycloakAdminService);
    redis = module.get<RedisService>(RedisService);
    http = module.get<HttpService>(HttpService);

    // Default mock for Admin Token retrieval
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

    it('should throw NotFoundException (AUTH_ACCOUNT_NOT_FOUND) if user does not exist locally and is not found on Keycloak', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);
      mockHttp.get.mockImplementation(() => {
        throw new Error('Not Found');
      });

      await expect(service.getMe('user-123', 'tenant-123')).rejects.toThrow(
        new NotFoundException({ errorCode: UserErrorCode.AUTH_ACCOUNT_NOT_FOUND, message: 'Auth account not found on Keycloak' })
      );
    });
  });

  describe('updateProfile', () => {
    const updateDto = { email: 'new@email.com', firstName: 'Jane', lastName: 'Doe', phoneNumber: '098111222' };

    it('should throw NotFoundException (USER_NOT_FOUND) if user does not exist locally', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.updateProfile('user-123', 'tenant-123', updateDto)).rejects.toThrow(
        new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User not found locally' })
      );
    });

    it('should throw ConflictException (EMAIL_ALREADY_IN_USE) if new email belongs to another Keycloak user', async () => {
      const mockUser = { id: 'user-123', tenantId: 'tenant-123' };
      mockPrisma.user.findUnique.mockResolvedValue(mockUser);
      mockHttp.get.mockReturnValue(of({ data: [{ id: 'user-456', email: 'new@email.com' }] }));

      await expect(service.updateProfile('user-123', 'tenant-123', updateDto)).rejects.toThrow(
        new ConflictException({ errorCode: UserErrorCode.EMAIL_ALREADY_IN_USE, message: 'Email is already in use by another account' })
      );
    });
  });

  describe('updatePreferences', () => {
    it('should throw NotFoundException (USER_PREFERENCES_NOT_FOUND) if user preferences record does not exist', async () => {
      mockPrisma.userPreference.findUnique.mockResolvedValue(null);

      await expect(service.updatePreferences('user-123', 'tenant-123', { theme: 'light' })).rejects.toThrow(
        new NotFoundException({ errorCode: UserErrorCode.USER_PREFERENCES_NOT_FOUND, message: 'User preferences not found' })
      );
    });
  });

  describe('inviteUser', () => {
    const inviteDto = { email: 'invite@email.com', firstName: 'Invited', lastName: 'User', department: 'Sales' };

    it('should return INVITE_SUCCESS response on successful invite', async () => {
      mockHttp.get.mockReturnValue(of({ data: [] })); // No duplicate user
      mockKeycloakAdmin.createUser.mockResolvedValue('kc-uuid-123');
      mockPrisma.user.create.mockResolvedValue({ id: 'kc-uuid-123' });

      const result = await service.inviteUser('tenant-123', inviteDto);

      expect(result).toEqual({
        success: true,
        code: UserSuccessCode.INVITE_SUCCESS,
        message: 'User invited successfully',
        userId: 'kc-uuid-123',
        activationLink: expect.stringContaining('/activate?token='),
      });
    });

    it('should throw ConflictException (EMAIL_ALREADY_IN_USE) if email already exists in Keycloak', async () => {
      mockHttp.get.mockReturnValue(of({ data: [{ id: 'existing-id' }] }));

      await expect(service.inviteUser('tenant-123', inviteDto)).rejects.toThrow(
        new ConflictException({ errorCode: UserErrorCode.EMAIL_ALREADY_IN_USE, message: 'User email already in use' })
      );
    });
  });

  describe('suspendUser', () => {
    it('should throw NotFoundException (USER_NOT_FOUND) if User is not found locally', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.suspendUser('tenant-123', 'user-123')).rejects.toThrow(
        new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User to suspend not found' })
      );
    });

    it('should throw ForbiddenException (TENANT_ACCESS_DENIED) if User belongs to a different tenant', async () => {
      mockPrisma.user.findUnique.mockResolvedValue({ id: 'user-123', tenantId: 'tenant-456' });

      await expect(service.suspendUser('tenant-123', 'user-123')).rejects.toThrow(
        new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' })
      );
    });
  });

  describe('unsuspendUser', () => {
    it('should throw NotFoundException (USER_NOT_FOUND) if User is not found locally', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      await expect(service.unsuspendUser('tenant-123', 'user-123')).rejects.toThrow(
        new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User to unsuspend not found' })
      );
    });

    it('should throw ForbiddenException (TENANT_ACCESS_DENIED) if User belongs to a different tenant', async () => {
      mockPrisma.user.findUnique.mockResolvedValue({ id: 'user-123', tenantId: 'tenant-456' });

      await expect(service.unsuspendUser('tenant-123', 'user-123')).rejects.toThrow(
        new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' })
      );
    });
  });
});

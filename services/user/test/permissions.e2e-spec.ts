import { Test, TestingModule } from '@nestjs/testing';
import { INestApplication } from '@nestjs/common';
import request from 'supertest';
import { App } from 'supertest/types';
import { AppModule } from './../src/app.module';
import { KeycloakAdminService } from '../src/keycloak/keycloak-admin.service';
import { PrismaService } from '../src/prisma/prisma.service';
import { UsersService } from '../src/users/users.service';
import * as crypto from 'crypto';

describe('PermissionsGuard & Custom Roles (e2e)', () => {
  let app: INestApplication<App>;
  let prisma: PrismaService;

  const tenantId = 'a0000000-0000-0000-0000-00000000000a';
  const userId = 'a1111111-1111-1111-1111-11111111111a';
  const signingSecret = process.env.GATEWAY_SIGNING_SECRET || 'default-gateway-signing-secret-key-change-me-in-production';

  const mockKeycloakAdminService = {
    createCustomRole: jest.fn().mockResolvedValue(undefined),
    deleteCustomRole: jest.fn().mockResolvedValue(undefined),
    assignCustomRoleToUser: jest.fn().mockResolvedValue(undefined),
    revokeCustomRoleFromUser: jest.fn().mockResolvedValue(undefined),
    createUser: jest.fn().mockResolvedValue('mock-user-id'),
    updateUser: jest.fn().mockResolvedValue(undefined),
    suspendUser: jest.fn().mockResolvedValue(undefined),
  };

  function generateSignature(tenant: string, user: string, permissions: string): string {
    const payload = `${tenant}:${user}:${permissions}`;
    return crypto.createHmac('sha256', signingSecret).update(payload).digest('hex');
  }

  beforeAll(async () => {
    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(KeycloakAdminService)
      .useValue(mockKeycloakAdminService)
      .compile();

    app = moduleFixture.createNestApplication();
    await app.init();

    prisma = moduleFixture.get<PrismaService>(PrismaService);

    // Clear and seed sample database records using a transaction with tenant_id set
    await prisma.$executeRawUnsafe(`TRUNCATE TABLE users CASCADE;`);
    await prisma.$transaction(async (tx) => {
      await tx.$executeRawUnsafe(`SET LOCAL app.current_tenant_id = '${tenantId}';`);
      await tx.user.create({
        data: {
          id: userId,
          tenantId: tenantId,
          status: 'ACTIVE',
          phoneNumber: '0901111111',
          preferences: { create: { theme: 'dark', language: 'vi' } },
        },
      });
    });
  });

  afterAll(async () => {
    await prisma.$executeRawUnsafe(`TRUNCATE TABLE users CASCADE;`);
    await app.close();
  });

  describe('GET /api/v1/permissions/manifest', () => {
    it('should deny access if headers are missing', async () => {
      await request(app.getHttpServer())
        .get('/api/v1/permissions/manifest')
        .expect(403);
    });

    it('should return permission manifest with valid signature', async () => {
      const perms = '';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/permissions/manifest')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body).toEqual({
        service: 'auth',
        resources: [
          {
            name: 'users',
            description: 'Tenant workspace users',
            actions: ['read', 'write', 'invite', 'suspend', 'unsuspend'],
          },
          {
            name: 'roles',
            description: 'Tenant workspace roles',
            actions: ['create', 'delete', 'assign', 'revoke'],
          },
        ],
      });
    });
  });

  describe('GET /api/v1/users/me (Timing-safe Signature & Header Verification)', () => {
    it('should deny access if headers are missing', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .expect(403);

      expect(response.body.message).toContain('Missing required security headers');
    });

    it('should deny access if signature is invalid', async () => {
      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', 'auth:users:read')
        .set('x-permissions-signature', 'invalid-signature')
        .expect(403);

      expect(response.body.message).toContain('Invalid permissions signature');
    });
  });

  describe('Dynamic RBAC checks', () => {
    it('should deny access if permissions are insufficient', async () => {
      const perms = 'auth:roles:create';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(403);

      expect(response.body.message).toContain('Insufficient permissions');
    });

    it('should allow access with exact match permission', async () => {
      const perms = 'auth:users:read';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.id).toBe(userId);
    });

    it('should allow access with service wildcard auth:*', async () => {
      const perms = 'auth:*';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.id).toBe(userId);
    });

    it('should deny access with global wildcard * if not master tenant', async () => {
      const perms = '*';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(403);

      expect(response.body.message).toContain('Insufficient permissions');
    });

    it('should allow access with global wildcard * if master tenant', async () => {
      const masterTenantId = 'solavie-system-master';
      const masterUserId = 'c1111111-1111-1111-1111-11111111111c';
      const perms = '*';
      const sig = generateSignature(masterTenantId, masterUserId, perms);

      // Mock getMe để tránh gọi vào DB và bị lỗi UUID
      const usersService = app.get<UsersService>(UsersService);
      const spy = jest.spyOn(usersService, 'getMe').mockResolvedValueOnce({
        id: masterUserId,
        tenantId: masterTenantId,
        status: 'ACTIVE',
      } as any);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', masterTenantId)
        .set('x-user-id', masterUserId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.id).toBe(masterUserId);
      spy.mockRestore();
    });

    it('should allow access with resource wildcard auth:users:*', async () => {
      const perms = 'auth:users:*';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .get('/api/v1/users/me')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.id).toBe(userId);
    });
  });

  describe('Custom Roles Management APIs', () => {
    it('should allow Admin to create a custom role', async () => {
      const perms = 'auth:roles:create';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .post('/api/v1/users/roles')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .send({ roleName: 'custom_manager' })
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(mockKeycloakAdminService.createCustomRole).toHaveBeenCalledWith(`${tenantId}:custom_manager`);
    });

    it('should block creating a reserved custom role', async () => {
      const perms = 'auth:roles:create';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .post('/api/v1/users/roles')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .send({ roleName: 'system' })
        .expect(400);

      expect(response.body.message).toContain('reserved and cannot be created or assigned');
    });

    it('should allow Admin to delete a custom role', async () => {
      const perms = 'auth:roles:delete';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .delete('/api/v1/users/roles/custom_manager')
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockKeycloakAdminService.deleteCustomRole).toHaveBeenCalledWith(`${tenantId}:custom_manager`);
    });

    it('should allow Admin to assign custom role to user', async () => {
      const perms = 'auth:roles:assign';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .post(`/api/v1/users/${userId}/roles`)
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .send({ roleName: 'custom_agent' })
        .expect(201);

      expect(response.body.success).toBe(true);
      expect(mockKeycloakAdminService.assignCustomRoleToUser).toHaveBeenCalledWith(userId, `${tenantId}:custom_agent`);
    });

    it('should block assigning a reserved custom role to user', async () => {
      const perms = 'auth:roles:assign';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .post(`/api/v1/users/${userId}/roles`)
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .send({ roleName: 'super_admin' })
        .expect(400);

      expect(response.body.message).toContain('reserved and cannot be created or assigned');
    });

    it('should allow Admin to revoke custom role from user', async () => {
      const perms = 'auth:roles:revoke';
      const sig = generateSignature(tenantId, userId, perms);

      const response = await request(app.getHttpServer())
        .delete(`/api/v1/users/${userId}/roles/custom_agent`)
        .set('x-tenant-id', tenantId)
        .set('x-user-id', userId)
        .set('x-user-permissions', perms)
        .set('x-permissions-signature', sig)
        .expect(200);

      expect(response.body.success).toBe(true);
      expect(mockKeycloakAdminService.revokeCustomRoleFromUser).toHaveBeenCalledWith(userId, `${tenantId}:custom_agent`);
    });
  });
});

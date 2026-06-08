import { Injectable, NotFoundException, ConflictException, ForbiddenException, BadRequestException, Logger } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { KeycloakAdminService } from '../keycloak/keycloak-admin.service';
import { RedisService } from '../redis/redis.service';
import { InviteUserDto } from './dto/invite-user.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdatePreferencesDto } from './dto/update-preferences.dto';
import * as crypto from 'crypto';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';
import { UserErrorCode, UserSuccessCode } from '../common/constants/user-codes';
import { tenantContextStorage } from '../common/context/tenant-context';

@Injectable()
export class UsersService {
  private readonly logger = new Logger(UsersService.name);
  private readonly keycloakUrl: string;

  constructor(
    private readonly prisma: PrismaService,
    private readonly keycloakAdmin: KeycloakAdminService,
    private readonly redis: RedisService,
    private readonly httpService: HttpService,
  ) {
    this.keycloakUrl = process.env.KEYCLOAK_URL || 'http://keycloak:8080';
  }

  /**
   * Lấy hồ sơ cá nhân hiện tại (bao gồm Preferences).
   * Áp dụng cơ chế Lazy Synchronization tự phục hồi khi người dùng đăng nhập lần đầu.
   */
  async getMe(userId: string, tenantId: string) {
    return this.prisma.runInTenantContext(async (tx) => {
      let user = await tx.user.findUnique({
        where: { id: userId },
        include: { preferences: true },
      });

      // Lazy Sync: Nếu user chưa tồn tại cục bộ hoặc trạng thái vẫn là PENDING
      if (!user || user.status === 'PENDING') {
        // Lấy thông tin user từ Keycloak để điền vào
        const token = await this.getAdminToken();
        let keycloakUser: any = null;
        try {
          const response = await firstValueFrom(
            this.httpService.get(`${this.keycloakUrl}/admin/realms/solavie/users/${userId}`, {
              headers: { Authorization: `Bearer ${token}` },
            }),
          );
          keycloakUser = response.data;
        } catch (e) {
          throw new NotFoundException({ errorCode: UserErrorCode.AUTH_ACCOUNT_NOT_FOUND, message: 'Auth account not found on Keycloak' });
        }

        if (!user) {
          // Tạo mới bản ghi User cục bộ với trạng thái ACTIVE
          user = await tx.user.create({
            data: {
              id: userId,
              tenantId: tenantId,
              status: 'ACTIVE',
              preferences: {
                create: {
                  theme: 'dark',
                  language: 'vi',
                },
              },
            },
            include: { preferences: true },
          });
        } else if (user.status === 'PENDING') {
          // Kích hoạt User sang ACTIVE
          user = await tx.user.update({
            where: { id: userId },
            data: { status: 'ACTIVE' },
            include: { preferences: true },
          });
        }
      }

      // Đọc thông tin họ tên, email trực tiếp từ Keycloak để merge vào kết quả trả về
      const token = await this.getAdminToken();
      let email = '';
      let firstName = '';
      let lastName = '';
      try {
        const response = await firstValueFrom(
          this.httpService.get(`${this.keycloakUrl}/admin/realms/solavie/users/${userId}`, {
            headers: { Authorization: `Bearer ${token}` },
          }),
        );
        email = response.data.email || '';
        firstName = response.data.firstName || '';
        lastName = response.data.lastName || '';
      } catch (e) {
        // Bỏ qua nếu lỗi
      }

      return {
        id: user.id,
        tenantId: user.tenantId,
        phoneNumber: user.phoneNumber,
        avatarUrl: user.avatarUrl,
        department: user.department,
        status: user.status,
        email,
        firstName,
        lastName,
        preferences: user.preferences,
        createdAt: user.createdAt,
        updatedAt: user.updatedAt,
      };
    });
  }

  /**
   * Cập nhật thông tin cá nhân.
   * Đồng bộ các trường Email, Họ, Tên lên Keycloak (sau khi check trùng email).
   */
  async updateProfile(userId: string, tenantId: string, data: UpdateProfileDto) {
    return this.prisma.runInTenantContext(async (tx) => {
      // 1. Kiểm tra sự tồn tại của User cục bộ
      const user = await tx.user.findUnique({ where: { id: userId } });
      if (!user) {
        throw new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User not found locally' });
      }

      // 2. Nếu có đổi email, kiểm tra chéo tính duy nhất trên Keycloak
      if (data.email) {
        const token = await this.getAdminToken();
        try {
          const response = await firstValueFrom(
            this.httpService.get(
              `${this.keycloakUrl}/admin/realms/solavie/users?email=${encodeURIComponent(data.email)}&exact=true`,
              {
                headers: { Authorization: `Bearer ${token}` },
              },
            ),
          );
          const usersWithEmail = response.data;
          if (usersWithEmail && usersWithEmail.length > 0) {
            const existingUser = usersWithEmail[0];
            if (existingUser.id !== userId) {
              throw new ConflictException({ errorCode: UserErrorCode.EMAIL_ALREADY_IN_USE, message: 'Email is already in use by another account' });
            }
          }
        } catch (e: any) {
          if (e instanceof ConflictException) throw e;
        }
      }

      // 3. Đồng bộ lên Keycloak các thông tin định tính
      if (data.email !== undefined || data.firstName !== undefined || data.lastName !== undefined) {
        await this.keycloakAdmin.updateUser('solavie', userId, {
          email: data.email,
          firstName: data.firstName,
          lastName: data.lastName,
        });
      }

      // 4. Cập nhật thông tin nghiệp vụ local
      const updatedUser = await tx.user.update({
        where: { id: userId },
        data: {
          phoneNumber: data.phoneNumber,
          avatarUrl: data.avatarUrl,
          department: data.department,
        },
      });

      return updatedUser;
    });
  }

  /**
   * Cập nhật cấu hình hiển thị cá nhân (Preferences).
   */
  async updatePreferences(userId: string, tenantId: string, data: UpdatePreferencesDto) {
    return this.prisma.runInTenantContext(async (tx) => {
      const preferences = await tx.userPreference.findUnique({ where: { userId } });
      if (!preferences) {
        throw new NotFoundException({ errorCode: UserErrorCode.USER_PREFERENCES_NOT_FOUND, message: 'User preferences not found' });
      }

      const updatedPrefs = await tx.userPreference.update({
        where: { userId },
        data: {
          theme: data.theme,
          language: data.language,
          notificationsEnabled: data.notificationsEnabled,
        },
      });

      return updatedPrefs;
    });
  }

  /**
   * Mời nhân viên (Chỉ Admin của Tenant mới được gọi).
   * Tạo tài khoản tạm thời trên Keycloak và DB local, sinh token kích hoạt.
   */
  async inviteUser(adminTenantId: string, data: InviteUserDto) {
    // 1. Kiểm tra email trùng trên Keycloak Realm solavie
    const token = await this.getAdminToken();
    try {
      const response = await firstValueFrom(
        this.httpService.get(
          `${this.keycloakUrl}/admin/realms/solavie/users?email=${encodeURIComponent(data.email)}&exact=true`,
          {
            headers: { Authorization: `Bearer ${token}` },
          },
        ),
      );
      if (response.data && response.data.length > 0) {
        throw new ConflictException({ errorCode: UserErrorCode.EMAIL_ALREADY_IN_USE, message: 'User email already in use' });
      }
    } catch (e: any) {
      if (e instanceof ConflictException) throw e;
    }

    // 2. Tạo User Shadow bị vô hiệu hóa trên Keycloak
    const keycloakUserId = await this.keycloakAdmin.createUser('solavie', {
      email: data.email,
      tenantId: adminTenantId,
      firstName: data.firstName,
      lastName: data.lastName,
    });

    // 3. Tạo bản ghi User cục bộ với trạng thái PENDING
    await this.prisma.runInTenantContext(async (tx) => {
      await tx.user.create({
        data: {
          id: keycloakUserId,
          tenantId: adminTenantId,
          department: data.department,
          status: 'PENDING',
          preferences: {
            create: {
              theme: 'dark',
              language: 'vi',
            },
          },
        },
      });
    });

    // 4. Sinh mã Token kích hoạt dùng một lần (TTL 24 giờ)
    const inviteToken = crypto.randomBytes(32).toString('hex');
    const invitePayload = JSON.stringify({
      userId: keycloakUserId,
      tenantId: adminTenantId,
      email: data.email,
    });

    await this.redis.setEx(`invite:token:${inviteToken}`, 86400, invitePayload);

    // Link kích hoạt tài khoản
    const activationLink = `${process.env.DASHBOARD_URL || 'http://localhost:3000'}/activate?token=${inviteToken}`;

    // 5. Bắn sự kiện sang Redis channel 'user.invited' để Notification Service gửi email
    const inviteEvent = {
      email: data.email,
      userId: keycloakUserId,
      tenantId: adminTenantId,
      activationLink,
      token: inviteToken,
    };
    await this.redis.publish('user.invited', JSON.stringify(inviteEvent));

    return {
      success: true,
      code: UserSuccessCode.INVITE_SUCCESS,
      message: 'User invited successfully',
      userId: keycloakUserId,
      activationLink,
    };
  }

  /**
   * Khóa tài khoản nhân viên (Admin Only).
   * Khóa trên Keycloak, force logout, đưa vào Redis Blacklist, cập nhật DB local.
   */
  async suspendUser(adminTenantId: string, targetUserId: string) {
    return this.prisma.runInTenantContext(async (tx) => {
      const user = await tx.user.findUnique({ where: { id: targetUserId } });
      if (!user) {
        throw new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User to suspend not found' });
      }
      if (user.tenantId !== adminTenantId) {
        throw new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' });
      }

      // 1. Gọi Keycloak Admin API đặt enabled=false và Force Logout sessions
      await this.keycloakAdmin.suspendUser('solavie', targetUserId);

      // 2. Ghi nhận User ID vào Redis Blacklist để Gateway chặn đứng tức thì
      await this.redis.setEx(`blacklist:user:${targetUserId}`, 900, 'suspended');

      // 3. Cập nhật trạng thái cục bộ sang SUSPENDED
      const updatedUser = await tx.user.update({
        where: { id: targetUserId },
        data: { status: 'SUSPENDED' },
      });

      return updatedUser;
    });
  }

  /**
   * Mở khóa tài khoản nhân viên (Admin Only).
   */
  async unsuspendUser(adminTenantId: string, targetUserId: string) {
    return this.prisma.runInTenantContext(async (tx) => {
      const user = await tx.user.findUnique({ where: { id: targetUserId } });
      if (!user) {
        throw new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User to unsuspend not found' });
      }
      if (user.tenantId !== adminTenantId) {
        throw new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' });
      }

      // 1. Kích hoạt lại trên Keycloak
      await this.keycloakAdmin.updateUser('solavie', targetUserId, { enabled: true });

      // 2. Xóa User ID khỏi Redis Blacklist
      const redisClient = this.redis.getClient();
      await redisClient.del(`blacklist:user:${targetUserId}`);

      // 3. Cập nhật trạng thái cục bộ sang ACTIVE
      const updatedUser = await tx.user.update({
        where: { id: targetUserId },
        data: { status: 'ACTIVE' },
      });

      return updatedUser;
    });
  }

  /**
   * Xác thực quyền truy cập nghiệp vụ của user (phục vụ gRPC RBAC)
   */
  async validateUserAccess(userId: string, tenantId: string, requiredRole: string): Promise<boolean> {
    const token = await this.getAdminToken();
    try {
      const response = await firstValueFrom(
        this.httpService.get(
          `${this.keycloakUrl}/admin/realms/solavie/users/${userId}/role-mappings/realm`,
          {
            headers: { Authorization: `Bearer ${token}` },
          },
        ),
      );
      const roles = response.data;
      if (!roles || roles.length === 0) return false;

      // So khớp không phân biệt hoa thường, hỗ trợ cả role mặc định và custom role prefix tenantId:
      const reqRoleLower = requiredRole.toLowerCase();
      const tenantRoleLower = `${tenantId.toLowerCase()}:${reqRoleLower}`;

      return roles.some((role: any) => {
        const roleNameLower = role.name.toLowerCase();
        return roleNameLower === reqRoleLower || roleNameLower === tenantRoleLower;
      });
    } catch (e) {
      return false;
    }
  }

  /**
   * Xử lý sự kiện đồng bộ từ Webhook Keycloak (KC -> US)
   */
  async handleWebhookEvent(payload: { event: string; userId: string; realm: string; email?: string }) {
    const { event, userId, realm, email } = payload;

    return tenantContextStorage.run({ tenantId: realm }, () => {
      return this.prisma.runInTenantContext(async (tx) => {
        switch (event) {
          case 'user.verified':
            await tx.user.upsert({
              where: { id: userId },
              create: {
                id: userId,
                tenantId: realm,
                status: 'ACTIVE',
                preferences: {
                  create: {
                    theme: 'dark',
                    language: 'vi',
                  },
                },
              },
              update: { status: 'ACTIVE' },
            });
            break;

          case 'user.disabled':
            await tx.user.updateMany({
              where: { id: userId },
              data: { status: 'SUSPENDED' },
            });
            break;

          case 'user.deleted':
            await tx.user.updateMany({
              where: { id: userId },
              data: { status: 'DELETED' },
            });
            break;

          case 'user.email_updated':
            this.logger.log(`User ${userId} in realm ${realm} updated email to ${email}`);
            break;

          default:
            this.logger.warn(`Unhandled Keycloak event: ${event}`);
        }
      });
    });
  }

  // --- Dynamic Custom Roles Management APIs ---

  /**
   * Tạo Custom Role động với prefix tenantId
   */
  async createCustomRole(tenantId: string, roleName: string): Promise<void> {
    const normalizedRole = roleName.trim().toLowerCase();
    if (['system', 'system_admin', 'super_admin', 'root'].includes(normalizedRole)) {
      throw new BadRequestException({
        errorCode: UserErrorCode.RESERVED_ROLE_BLOCKED,
        message: `Role name '${roleName}' is reserved and cannot be created or assigned.`,
      });
    }
    const fullRoleName = `${tenantId}:${roleName}`;
    await this.keycloakAdmin.createCustomRole(fullRoleName);
  }

  /**
   * Xóa Custom Role động
   */
  async deleteCustomRole(tenantId: string, roleName: string): Promise<void> {
    const fullRoleName = `${tenantId}:${roleName}`;
    await this.keycloakAdmin.deleteCustomRole(fullRoleName);
  }

  /**
   * Gán Custom Role cho người dùng (chỉ được gán cho user cùng tenant)
   */
  async assignRoleToUser(tenantId: string, userId: string, roleName: string): Promise<void> {
    const normalizedRole = roleName.trim().toLowerCase();
    if (['system', 'system_admin', 'super_admin', 'root'].includes(normalizedRole)) {
      throw new BadRequestException({
        errorCode: UserErrorCode.RESERVED_ROLE_BLOCKED,
        message: `Role name '${roleName}' is reserved and cannot be created or assigned.`,
      });
    }

    // Verify user belongs to tenant first
    const user = await this.prisma.runInTenantContext(async (tx) => {
      return tx.user.findUnique({ where: { id: userId } });
    });
    if (!user) {
      throw new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User not found locally' });
    }
    if (user.tenantId !== tenantId) {
      throw new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' });
    }

    const fullRoleName = `${tenantId}:${roleName}`;
    await this.keycloakAdmin.assignCustomRoleToUser(userId, fullRoleName);
  }

  /**
   * Thu hồi Custom Role từ người dùng
   */
  async revokeRoleFromUser(tenantId: string, userId: string, roleName: string): Promise<void> {
    // Verify user belongs to tenant
    const user = await this.prisma.runInTenantContext(async (tx) => {
      return tx.user.findUnique({ where: { id: userId } });
    });
    if (!user) {
      throw new NotFoundException({ errorCode: UserErrorCode.USER_NOT_FOUND, message: 'User not found locally' });
    }
    if (user.tenantId !== tenantId) {
      throw new ForbiddenException({ errorCode: UserErrorCode.TENANT_ACCESS_DENIED, message: 'Access denied: Target user belongs to a different tenant' });
    }

    const fullRoleName = `${tenantId}:${roleName}`;
    await this.keycloakAdmin.revokeCustomRoleFromUser(userId, fullRoleName);
  }

  /**
   * Helper lấy Admin token phục vụ các request HTTP (Client Credentials Flow)
   */
  private async getAdminToken(): Promise<string> {
    const url = `${this.keycloakUrl}/realms/solavie/protocol/openid-connect/token`;
    const params = new URLSearchParams();
    params.append('client_id', 'user-service-client');
    params.append('client_secret', process.env.KEYCLOAK_CLIENT_SECRET || 'default-user-service-client-secret-key-change-me-in-production');
    params.append('grant_type', 'client_credentials');

    try {
      const response = await firstValueFrom(
        this.httpService.post(url, params, {
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        }),
      );
      return response.data.access_token;
    } catch (e: any) {
      throw new Error(`Failed to fetch Keycloak admin token: ${e.message}`);
    }
  }
}

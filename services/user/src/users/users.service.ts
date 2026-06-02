import { Injectable, NotFoundException, ConflictException, ForbiddenException, BadRequestException } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';
import { KeycloakAdminService } from '../keycloak/keycloak-admin.service';
import { RedisService } from '../redis/redis.service';
import { InviteUserDto } from './dto/invite-user.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdatePreferencesDto } from './dto/update-preferences.dto';
import * as crypto from 'crypto';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class UsersService {
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
            this.httpService.get(`${this.keycloakUrl}/admin/realms/${tenantId}/users/${userId}`, {
              headers: { Authorization: `Bearer ${token}` },
            }),
          );
          keycloakUser = response.data;
        } catch (e) {
          // Nếu không tìm thấy trên Keycloak, ta ném lỗi
          throw new NotFoundException('Không tìm thấy tài khoản tương ứng trên máy chủ xác thực.');
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
          this.httpService.get(`${this.keycloakUrl}/admin/realms/${tenantId}/users/${userId}`, {
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
        throw new NotFoundException('Không tìm thấy tài khoản người dùng.');
      }

      // 2. Nếu có đổi email, kiểm tra chéo tính duy nhất trên Keycloak
      if (data.email) {
        const token = await this.getAdminToken();
        try {
          const response = await firstValueFrom(
            this.httpService.get(
              `${this.keycloakUrl}/admin/realms/${tenantId}/users?email=${encodeURIComponent(data.email)}&exact=true`,
              {
                headers: { Authorization: `Bearer ${token}` },
              },
            ),
          );
          const usersWithEmail = response.data;
          if (usersWithEmail && usersWithEmail.length > 0) {
            const existingUser = usersWithEmail[0];
            if (existingUser.id !== userId) {
              throw new ConflictException('Email này đã được sử dụng bởi tài khoản khác.');
            }
          }
        } catch (e: any) {
          if (e instanceof ConflictException) throw e;
          // Bỏ qua các lỗi mạng khác
        }
      }

      // 3. Đồng bộ lên Keycloak các thông tin định tính
      if (data.email !== undefined || data.firstName !== undefined || data.lastName !== undefined) {
        await this.keycloakAdmin.updateUser(tenantId, userId, {
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
        throw new NotFoundException('Không tìm thấy cấu hình cá nhân của người dùng.');
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
    // 1. Kiểm tra email trùng trên Keycloak Realm của Tenant
    const token = await this.getAdminToken();
    try {
      const response = await firstValueFrom(
        this.httpService.get(
          `${this.keycloakUrl}/admin/realms/${adminTenantId}/users?email=${encodeURIComponent(data.email)}&exact=true`,
          {
            headers: { Authorization: `Bearer ${token}` },
          },
        ),
      );
      if (response.data && response.data.length > 0) {
        throw new ConflictException('Nhân viên có email này đã tồn tại trong hệ thống.');
      }
    } catch (e: any) {
      if (e instanceof ConflictException) throw e;
    }

    // 2. Tạo User Shadow bị vô hiệu hóa trên Keycloak
    const keycloakUserId = await this.keycloakAdmin.createUser(adminTenantId, {
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

    // Lưu vào Redis với TTL 24 giờ (86400 giây)
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
      message: 'Gửi lời mời thành công.',
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
        throw new NotFoundException('Không tìm thấy nhân viên cần khóa.');
      }
      if (user.tenantId !== adminTenantId) {
        throw new ForbiddenException('Bạn không có quyền quản lý nhân viên của doanh nghiệp khác.');
      }

      // 1. Gọi Keycloak Admin API đặt enabled=false và Force Logout sessions
      await this.keycloakAdmin.suspendUser(adminTenantId, targetUserId);

      // 2. Ghi nhận User ID vào Redis Blacklist để Gateway chặn đứng tức thì
      // Access Token sống tối đa 15 phút (900 giây)
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
        throw new NotFoundException('Không tìm thấy nhân viên cần mở khóa.');
      }
      if (user.tenantId !== adminTenantId) {
        throw new ForbiddenException('Bạn không có quyền quản lý nhân viên của doanh nghiệp khác.');
      }

      // 1. Kích hoạt lại trên Keycloak
      await this.keycloakAdmin.updateUser(adminTenantId, targetUserId, { enabled: true });

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
          `${this.keycloakUrl}/admin/realms/${tenantId}/users/${userId}/role-mappings/realm`,
          {
            headers: { Authorization: `Bearer ${token}` },
          },
        ),
      );
      const roles = response.data;
      if (!roles || roles.length === 0) return false;

      // So khớp không phân biệt hoa thường
      return roles.some((role: any) => role.name.toLowerCase() === requiredRole.toLowerCase());
    } catch (e) {
      return false;
    }
  }

  /**
   * Xử lý sự kiện đồng bộ từ Webhook Keycloak (KC -> US)
   */
  async handleWebhookEvent(payload: { event: string; userId: string; realm: string; email?: string }) {
    const { event, userId, realm, email } = payload;

    // Webhook chạy với quyền toàn cục hệ thống (bypass RLS vì getTenantId() trả về undefined)
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
          // Xóa mềm (Soft Delete) hồ sơ nghiệp vụ bằng cách đổi trạng thái sang DELETED
          await tx.user.updateMany({
            where: { id: userId },
            data: { status: 'DELETED' },
          });
          break;

        case 'user.email_updated':
          // Cục bộ DB chỉ cache thông tin nghiệp vụ, thông tin email được lưu trên Keycloak
          console.log(`User ${userId} in realm ${realm} updated email to ${email}`);
          break;

        default:
          console.log(`Unhandled Keycloak event: ${event}`);
      }
    });
  }

  /**
   * Helper lấy Admin token phục vụ các request HTTP
   */
  private async getAdminToken(): Promise<string> {
    const url = `${this.keycloakUrl}/realms/master/protocol/openid-connect/token`;
    const params = new URLSearchParams();
    params.append('client_id', 'admin-cli');
    params.append('username', process.env.KC_ADMIN || 'admin');
    params.append('password', process.env.KC_ADMIN_PASSWORD || 'admin_secret_pass');
    params.append('grant_type', 'password');

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

import { Controller, Get, Put, Post, Delete, Body, Headers, Param, HttpCode, HttpStatus, UseGuards, BadRequestException } from '@nestjs/common';
import { UsersService } from './users.service';
import { InviteUserDto } from './dto/invite-user.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdatePreferencesDto } from './dto/update-preferences.dto';
import { WebhookGuard } from '../common/guards/webhook.guard';
import { PermissionsGuard } from '../common/guards/permissions.guard';
import { RequiredPermission } from '../common/decorators/required-permission.decorator';

@Controller('api/v1/users')
@UseGuards(PermissionsGuard)
export class UsersController {
  constructor(private readonly usersService: UsersService) { }

  /**
   * GET /api/v1/users/me
   * Lấy hồ sơ người dùng hiện tại
   */
  @Get('me')
  @RequiredPermission('auth:users:read')
  async getMe(
    @Headers('x-user-id') userId: string,
    @Headers('x-tenant-id') tenantId: string,
  ) {
    return this.usersService.getMe(userId, tenantId);
  }

  /**
   * PUT /api/v1/users/profile
   * Cập nhật hồ sơ cá nhân
   */
  @Put('profile')
  @RequiredPermission('auth:users:write')
  async updateProfile(
    @Headers('x-user-id') userId: string,
    @Headers('x-tenant-id') tenantId: string,
    @Body() updateProfileDto: UpdateProfileDto,
  ) {
    return this.usersService.updateProfile(userId, tenantId, updateProfileDto);
  }

  /**
   * PUT /api/v1/users/preferences
   * Cập nhật cấu hình hiển thị cá nhân
   */
  @Put('preferences')
  @RequiredPermission('auth:users:write')
  async updatePreferences(
    @Headers('x-user-id') userId: string,
    @Headers('x-tenant-id') tenantId: string,
    @Body() updatePreferencesDto: UpdatePreferencesDto,
  ) {
    return this.usersService.updatePreferences(userId, tenantId, updatePreferencesDto);
  }

  /**
   * POST /api/v1/users/invite
   * Mời nhân viên mới vào doanh nghiệp (Admin Only)
   */
  @Post('invite')
  @HttpCode(HttpStatus.CREATED)
  @RequiredPermission('auth:users:invite')
  async inviteUser(
    @Headers('x-tenant-id') adminTenantId: string,
    @Body() inviteUserDto: InviteUserDto,
  ) {
    return this.usersService.inviteUser(adminTenantId, inviteUserDto);
  }

  /**
   * POST /api/v1/users/:id/suspend
   * Khóa tài khoản nhân viên (Admin Only)
   */
  @Post(':id/suspend')
  @RequiredPermission('auth:users:suspend')
  async suspendUser(
    @Headers('x-tenant-id') adminTenantId: string,
    @Param('id') targetUserId: string,
  ) {
    return this.usersService.suspendUser(adminTenantId, targetUserId);
  }

  /**
   * POST /api/v1/users/:id/unsuspend
   * Mở khóa tài khoản nhân viên (Admin Only)
   */
  @Post(':id/unsuspend')
  @RequiredPermission('auth:users:unsuspend')
  async unsuspendUser(
    @Headers('x-tenant-id') adminTenantId: string,
    @Param('id') targetUserId: string,
  ) {
    return this.usersService.unsuspendUser(adminTenantId, targetUserId);
  }

  /**
   * POST /api/v1/users/roles
   * Tạo vai trò tùy chỉnh mới (Admin Only)
   */
  @Post('roles')
  @RequiredPermission('auth:roles:create')
  async createCustomRole(
    @Headers('x-tenant-id') tenantId: string,
    @Body('roleName') roleName: string,
  ) {
    if (!roleName) {
      throw new BadRequestException('roleName is required');
    }
    await this.usersService.createCustomRole(tenantId, roleName);
    return { success: true, message: `Role ${roleName} created successfully` };
  }

  /**
   * DELETE /api/v1/users/roles/:name
   * Xóa vai trò tùy chỉnh (Admin Only)
   */
  @Delete('roles/:name')
  @RequiredPermission('auth:roles:delete')
  async deleteCustomRole(
    @Headers('x-tenant-id') tenantId: string,
    @Param('name') roleName: string,
  ) {
    await this.usersService.deleteCustomRole(tenantId, roleName);
    return { success: true, message: `Role ${roleName} deleted successfully` };
  }

  /**
   * POST /api/v1/users/:id/roles
   * Gán vai trò tùy chỉnh cho người dùng (Admin Only)
   */
  @Post(':id/roles')
  @RequiredPermission('auth:roles:assign')
  async assignRoleToUser(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') userId: string,
    @Body('roleName') roleName: string,
  ) {
    if (!roleName) {
      throw new BadRequestException('roleName is required');
    }
    await this.usersService.assignRoleToUser(tenantId, userId, roleName);
    return { success: true, message: `Role ${roleName} assigned to user ${userId}` };
  }

  /**
   * DELETE /api/v1/users/:id/roles/:name
   * Thu hồi vai trò tùy chỉnh từ người dùng (Admin Only)
   */
  @Delete(':id/roles/:name')
  @RequiredPermission('auth:roles:revoke')
  async revokeRoleFromUser(
    @Headers('x-tenant-id') tenantId: string,
    @Param('id') userId: string,
    @Param('name') roleName: string,
  ) {
    await this.usersService.revokeRoleFromUser(tenantId, userId, roleName);
    return { success: true, message: `Role ${roleName} revoked from user ${userId}` };
  }

  /**
   * POST /api/v1/users/events
   * Webhook tiếp nhận sự kiện từ Keycloak Identity Provider
   */
  @Post('events')
  @UseGuards(WebhookGuard)
  @HttpCode(HttpStatus.OK)
  async handleWebhookEvent(
    @Body() payload: { event: string; userId: string; realm: string; email?: string },
  ) {
    return this.usersService.handleWebhookEvent(payload);
  }
}

import { Controller, Get, Put, Post, Body, Headers, Param, HttpCode, HttpStatus, UseGuards } from '@nestjs/common';
import { UsersService } from './users.service';
import { InviteUserDto } from './dto/invite-user.dto';
import { UpdateProfileDto } from './dto/update-profile.dto';
import { UpdatePreferencesDto } from './dto/update-preferences.dto';
import { WebhookGuard } from '../common/guards/webhook.guard';

@Controller('api/v1/users')
export class UsersController {
  constructor(private readonly usersService: UsersService) {}

  /**
   * GET /api/v1/users/me
   * Lấy hồ sơ người dùng hiện tại
   */
  @Get('me')
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
  async unsuspendUser(
    @Headers('x-tenant-id') adminTenantId: string,
    @Param('id') targetUserId: string,
  ) {
    return this.usersService.unsuspendUser(adminTenantId, targetUserId);
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

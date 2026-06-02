import { Controller } from '@nestjs/common';
import { GrpcMethod } from '@nestjs/microservices';
import { UsersService } from './users.service';
import { Metadata } from '@grpc/grpc-js';

interface GetUserProfileRequest {
  userId: string;
  tenantId: string;
}

interface GetUserProfileResponse {
  userId: string;
  tenantId: string;
  phoneNumber: string;
  avatarUrl: string;
  department: string;
  status: string;
}

interface ValidateUserAccessRequest {
  userId: string;
  tenantId: string;
  requiredRole: string;
}

interface ValidateUserAccessResponse {
  isAllowed: boolean;
}

@Controller()
export class UsersGrpcController {
  constructor(private readonly usersService: UsersService) {}

  /**
   * RPC GetUserProfile
   * Lấy hồ sơ nhân viên nghiệp vụ (có tự phục hồi Lazy Sync)
   */
  @GrpcMethod('UserService', 'GetUserProfile')
  async getUserProfile(
    data: GetUserProfileRequest,
    metadata: Metadata,
    call: any,
  ): Promise<GetUserProfileResponse> {
    const profile = await this.usersService.getMe(data.userId, data.tenantId);
    return {
      userId: profile.id,
      tenantId: profile.tenantId,
      phoneNumber: profile.phoneNumber || '',
      avatarUrl: profile.avatarUrl || '',
      department: profile.department || '',
      status: profile.status,
    };
  }

  /**
   * RPC ValidateUserAccess
   * Xác thực phân quyền chéo dịch vụ (RBAC)
   */
  @GrpcMethod('UserService', 'ValidateUserAccess')
  async validateUserAccess(
    data: ValidateUserAccessRequest,
    metadata: Metadata,
    call: any,
  ): Promise<ValidateUserAccessResponse> {
    const isAllowed = await this.usersService.validateUserAccess(
      data.userId,
      data.tenantId,
      data.requiredRole,
    );
    return { isAllowed };
  }
}

import { Injectable, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class KeycloakAdminService {
  private readonly keycloakUrl: string;

  constructor(private readonly httpService: HttpService) {
    this.keycloakUrl = process.env.KEYCLOAK_URL || 'http://keycloak:8080';
  }

  /**
   * Lấy Admin Access Token bằng Client Credentials flow từ Realm solavie
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
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to obtain Keycloak admin token: ${errorMsg}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Tìm Organization ID theo Alias (chính là tenantId)
   */
  async getOrganizationByAlias(alias: string): Promise<string> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/organizations`;
    try {
      const response = await firstValueFrom(
        this.httpService.get(url, {
          headers: { Authorization: `Bearer ${token}` },
          params: { max: 1000 },
        }),
      );
      const orgs = response.data;
      const org = orgs.find((o: any) => o.alias === alias);
      if (!org) {
        throw new HttpException(
          `Organization not found for alias: ${alias}`,
          HttpStatus.NOT_FOUND,
        );
      }
      return org.id;
    } catch (error: any) {
      if (error instanceof HttpException) throw error;
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to fetch organization by alias: ${errorMsg}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Liên kết User vào Organization làm thành viên
   */
  async addMemberToOrg(orgId: string, userId: string): Promise<void> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/organizations/${orgId}/members`;
    try {
      await firstValueFrom(
        this.httpService.post(url, JSON.stringify(userId), {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }),
      );
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to link member to organization: ${errorMsg}`,
        HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Tạo User Shadow trong Realm solavie và link vào Organization
   * @returns Keycloak User UUID
   */
  async createUser(
    realm: string, // Phớt lờ tham số realm cũ, luôn luôn dùng realm solavie
    userPayload: { email: string; tenantId: string; firstName?: string; lastName?: string },
  ): Promise<string> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/users`;

    try {
      const response = await firstValueFrom(
        this.httpService.post(
          url,
          {
            username: userPayload.email,
            email: userPayload.email,
            enabled: false,
            emailVerified: false,
            firstName: userPayload.firstName,
            lastName: userPayload.lastName,
            attributes: {
              tenant_id: [userPayload.tenantId],
            },
          },
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          },
        ),
      );

      const locationHeader = response.headers['location'];
      if (!locationHeader) {
        throw new Error('Location header missing in Keycloak response');
      }
      const parts = locationHeader.split('/');
      const userId = parts[parts.length - 1];

      // Liên kết User vào Organization
      try {
        const orgId = await this.getOrganizationByAlias(userPayload.tenantId);
        await this.addMemberToOrg(orgId, userId);
      } catch (e: any) {
        throw new HttpException(
          `User created on Keycloak but failed to link to Organization '${userPayload.tenantId}': ${e.message}`,
          HttpStatus.INTERNAL_SERVER_ERROR,
        );
      }

      return userId;
    } catch (error: any) {
      if (error instanceof HttpException) throw error;
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to create user on Keycloak: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Cập nhật User trên Keycloak
   */
  async updateUser(
    realm: string, // Phớt lờ, luôn dùng solavie
    userId: string,
    updatePayload: { email?: string; firstName?: string; lastName?: string; enabled?: boolean },
  ): Promise<void> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/users/${userId}`;

    const body: any = {};
    if (updatePayload.email !== undefined) {
      body.email = updatePayload.email;
      body.username = updatePayload.email;
    }
    if (updatePayload.firstName !== undefined) body.firstName = updatePayload.firstName;
    if (updatePayload.lastName !== undefined) body.lastName = updatePayload.lastName;
    if (updatePayload.enabled !== undefined) body.enabled = updatePayload.enabled;

    try {
      await firstValueFrom(
        this.httpService.put(url, body, {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }),
      );
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to update user on Keycloak: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Khóa user và Force Logout hủy toàn bộ session hoạt động
   */
  async suspendUser(realm: string, userId: string): Promise<void> {
    // 1. Disable user
    await this.updateUser('solavie', userId, { enabled: false });

    // 2. Force logout
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/users/${userId}/logout`;

    try {
      await firstValueFrom(
        this.httpService.post(
          url,
          {},
          {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          },
        ),
      );
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to logout user on Keycloak: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Tạo Custom Role trong realm solavie
   */
  async createCustomRole(roleName: string): Promise<void> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/roles`;
    try {
      await firstValueFrom(
        this.httpService.post(
          url,
          { name: roleName },
          {
            headers: {
              Authorization: `Bearer ${token}`,
              'Content-Type': 'application/json',
            },
          },
        ),
      );
    } catch (error: any) {
      if (error.response?.status === HttpStatus.CONFLICT) {
        return; // Đã tồn tại
      }
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to create custom role on Keycloak: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Xóa Custom Role khỏi realm solavie
   */
  async deleteCustomRole(roleName: string): Promise<void> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/solavie/roles/${roleName}`;
    try {
      await firstValueFrom(
        this.httpService.delete(url, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      );
    } catch (error: any) {
      if (error.response?.status === HttpStatus.NOT_FOUND) {
        return;
      }
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to delete custom role from Keycloak: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Gán Custom Role cho người dùng
   */
  async assignCustomRoleToUser(userId: string, roleName: string): Promise<void> {
    const token = await this.getAdminToken();
    
    // 1. Lấy representation của role
    const getRoleUrl = `${this.keycloakUrl}/admin/realms/solavie/roles/${roleName}`;
    let roleRep: any = null;
    try {
      const response = await firstValueFrom(
        this.httpService.get(getRoleUrl, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      );
      roleRep = response.data;
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to fetch role '${roleName}' representation: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }

    // 2. Gán role mapping cho user
    const assignUrl = `${this.keycloakUrl}/admin/realms/solavie/users/${userId}/role-mappings/realm`;
    try {
      await firstValueFrom(
        this.httpService.post(assignUrl, [roleRep], {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }),
      );
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to assign role '${roleName}' to user: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  /**
   * Thu hồi Custom Role từ người dùng
   */
  async revokeCustomRoleFromUser(userId: string, roleName: string): Promise<void> {
    const token = await this.getAdminToken();
    
    // 1. Lấy representation của role
    const getRoleUrl = `${this.keycloakUrl}/admin/realms/solavie/roles/${roleName}`;
    let roleRep: any = null;
    try {
      const response = await firstValueFrom(
        this.httpService.get(getRoleUrl, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      );
      roleRep = response.data;
    } catch (error: any) {
      if (error.response?.status === HttpStatus.NOT_FOUND) {
        return;
      }
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to fetch role '${roleName}' representation: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }

    // 2. Xóa mapping role
    const revokeUrl = `${this.keycloakUrl}/admin/realms/solavie/users/${userId}/role-mappings/realm`;
    try {
      await firstValueFrom(
        this.httpService.delete(revokeUrl, {
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          data: [roleRep],
        }),
      );
    } catch (error: any) {
      const errorMsg = error.response?.data ? JSON.stringify(error.response.data) : error.message;
      throw new HttpException(
        `Failed to revoke role '${roleName}' from user: ${errorMsg}`,
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}

import { Injectable, HttpException, HttpStatus } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import { firstValueFrom } from 'rxjs';

@Injectable()
export class KeycloakAdminService {
  private readonly keycloakUrl: string;
  private readonly adminUser: string;
  private readonly adminPass: string;

  constructor(private readonly httpService: HttpService) {
    // Trong môi trường docker, KEYCLOAK_URL sẽ trỏ sang http://keycloak:8080
    // Khi chạy test cục bộ, có thể override sang cổng 8081
    this.keycloakUrl = process.env.KEYCLOAK_URL || 'http://keycloak:8080';
    this.adminUser = process.env.KC_ADMIN || 'admin';
    this.adminPass = process.env.KC_ADMIN_PASSWORD || 'admin_secret_pass';
  }

  /**
   * Lấy Admin Access Token từ Realm master
   */
  private async getAdminToken(): Promise<string> {
    const url = `${this.keycloakUrl}/realms/master/protocol/openid-connect/token`;
    const params = new URLSearchParams();
    params.append('client_id', 'admin-cli');
    params.append('username', this.adminUser);
    params.append('password', this.adminPass);
    params.append('grant_type', 'password');

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
   * Tạo User Shadow trong Realm của Tenant
   * @returns Keycloak User UUID
   */
  async createUser(
    realm: string,
    userPayload: { email: string; tenantId: string; firstName?: string; lastName?: string },
  ): Promise<string> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/${realm}/users`;

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
      return parts[parts.length - 1];
    } catch (error: any) {
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
    realm: string,
    userId: string,
    updatePayload: { email?: string; firstName?: string; lastName?: string; enabled?: boolean },
  ): Promise<void> {
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/${realm}/users/${userId}`;

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
    await this.updateUser(realm, userId, { enabled: false });

    // 2. Force logout
    const token = await this.getAdminToken();
    const url = `${this.keycloakUrl}/admin/realms/${realm}/users/${userId}/logout`;

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
}

import { Injectable, CanActivate, ExecutionContext, ForbiddenException } from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import * as crypto from 'crypto';
import { REQUIRED_PERMISSION_KEY } from '../decorators/required-permission.decorator';

@Injectable()
export class PermissionsGuard implements CanActivate {
  constructor(private reflector: Reflector) {}

  canActivate(context: ExecutionContext): boolean {
    const requiredPermission = this.reflector.get<string>(
      REQUIRED_PERMISSION_KEY,
      context.getHandler(),
    );

    const request = context.switchToHttp().getRequest();
    const tenantId = request.headers['x-tenant-id'];
    const userId = request.headers['x-user-id'];
    const userPermissionsHeader = request.headers['x-user-permissions'];
    const signature = request.headers['x-permissions-signature'];

    if (!tenantId || !userId || userPermissionsHeader === undefined || !signature) {
      throw new ForbiddenException('Missing required security headers');
    }

    // 1. HMAC-SHA256 Signature Verification
    const secret = process.env.GATEWAY_SIGNING_SECRET || 'default-gateway-signing-secret-key-change-me-in-production';
    const payload = `${tenantId}:${userId}:${userPermissionsHeader}`;
    const expectedSignature = crypto
      .createHmac('sha256', secret)
      .update(payload)
      .digest('hex');

    try {
      const a = Buffer.from(signature, 'hex');
      const b = Buffer.from(expectedSignature, 'hex');
      if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) {
        throw new ForbiddenException('Invalid permissions signature');
      }
    } catch (e) {
      throw new ForbiddenException('Invalid permissions signature');
    }

    // Nếu endpoint không yêu cầu permission đặc thù, cho qua.
    if (!requiredPermission) {
      return true;
    }

    // 2. Dynamic RBAC Wildcard Matching in-memory O(1)
    const permissions = new Set<string>(
      userPermissionsHeader ? userPermissionsHeader.split(',').map((p: string) => p.trim()) : [],
    );

    if (this.hasPermission(permissions, requiredPermission, tenantId)) {
      return true;
    }

    throw new ForbiddenException('Insufficient permissions');
  }

  private hasPermission(permissions: Set<string>, required: string, tenantId: string): boolean {
    // Super Admin wildcard - Only allowed in master tenant
    if (permissions.has('*') && tenantId === 'solavie-system-master') {
      return true;
    }

    // Exact match
    if (permissions.has(required)) {
      return true;
    }

    // Wildcard matching: auth:* hoặc auth:users:*
    const parts = required.split(':');
    if (parts.length >= 2) {
      const service = parts[0];
      const resource = parts[1];

      // auth:*
      if (permissions.has(`${service}:*`)) {
        return true;
      }

      // auth:users:*
      if (permissions.has(`${service}:${resource}:*`)) {
        return true;
      }
    }

    return false;
  }
}

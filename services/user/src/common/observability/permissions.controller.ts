import { Controller, Get, UseGuards } from '@nestjs/common';
import { PermissionsGuard } from '../guards/permissions.guard';

@Controller('api/v1/permissions')
@UseGuards(PermissionsGuard)
export class PermissionsController {
  @Get('manifest')
  getManifest() {
    return {
      service: 'auth',
      resources: [
        {
          name: 'users',
          description: 'Tenant workspace users',
          actions: [
            'read',
            'write',
            'invite',
            'suspend',
            'unsuspend',
          ],
        },
        {
          name: 'roles',
          description: 'Tenant workspace roles',
          actions: [
            'create',
            'delete',
            'assign',
            'revoke',
          ],
        },
      ],
    };
  }
}

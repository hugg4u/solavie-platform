import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { KeycloakAdminService } from './keycloak-admin.service';

@Module({
  imports: [HttpModule],
  providers: [KeycloakAdminService],
  exports: [KeycloakAdminService],
})
export class KeycloakModule {}

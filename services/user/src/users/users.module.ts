import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { UsersController } from './users.controller';
import { UsersGrpcController } from './users.grpc.controller';
import { UsersService } from './users.service';
import { KeycloakModule } from '../keycloak/keycloak.module';

@Module({
  imports: [HttpModule, KeycloakModule],
  controllers: [UsersController, UsersGrpcController],
  providers: [UsersService],
  exports: [UsersService],
})
export class UsersModule {}

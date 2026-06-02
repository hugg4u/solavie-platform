import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { RedisModule } from './redis/redis.module';
import { KeycloakModule } from './keycloak/keycloak.module';
import { UsersModule } from './users/users.module';
import { TenantMiddleware } from './common/middleware/tenant.middleware';

@Module({
  imports: [PrismaModule, RedisModule, KeycloakModule, UsersModule],
  controllers: [AppController],
  providers: [AppService],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(TenantMiddleware).forRoutes('*');
  }
}

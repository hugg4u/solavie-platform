import { Module, NestModule, MiddlewareConsumer } from '@nestjs/common';
import { APP_INTERCEPTOR } from '@nestjs/core';
import { AppController } from './app.controller';
import { AppService } from './app.service';
import { PrismaModule } from './prisma/prisma.module';
import { RedisModule } from './redis/redis.module';
import { KeycloakModule } from './keycloak/keycloak.module';
import { UsersModule } from './users/users.module';
import { TenantMiddleware } from './common/middleware/tenant.middleware';
import { HealthController } from './common/observability/health.controller';
import { PermissionsController } from './common/observability/permissions.controller';
import { MetricsService } from './common/observability/metrics.service';
import { MetricsInterceptor } from './common/observability/metrics.interceptor';
import { ServiceRegistryClient } from './common/observability/service-registry.client';

@Module({
  imports: [PrismaModule, RedisModule, KeycloakModule, UsersModule],
  controllers: [AppController, HealthController, PermissionsController],
  providers: [
    AppService,
    MetricsService,
    ServiceRegistryClient,
    {
      provide: APP_INTERCEPTOR,
      useClass: MetricsInterceptor,
    },
  ],
})
export class AppModule implements NestModule {
  configure(consumer: MiddlewareConsumer) {
    consumer.apply(TenantMiddleware).forRoutes('*');
  }
}

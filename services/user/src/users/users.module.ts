import { Module } from '@nestjs/common';
import { HttpModule } from '@nestjs/axios';
import { ClientsModule, Transport } from '@nestjs/microservices';
import { UsersController } from './users.controller';
import { UsersGrpcController } from './users.grpc.controller';
import { UsersKafkaController } from './users.kafka.controller';
import { UsersService } from './users.service';
import { KeycloakModule } from '../keycloak/keycloak.module';

@Module({
  imports: [
    HttpModule,
    KeycloakModule,
    ClientsModule.register([
      {
        name: 'KAFKA_SERVICE',
        transport: Transport.KAFKA,
        options: {
          client: {
            clientId: 'user-service',
            brokers: [process.env.KAFKA_BROKER || 'kafka:9092'],
          },
          consumer: {
            groupId: 'user-service-producer-group',
          },
        },
      },
    ]),
  ],
  controllers: [UsersController, UsersGrpcController, UsersKafkaController],
  providers: [UsersService],
  exports: [UsersService],
})
export class UsersModule { }

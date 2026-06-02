import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { MicroserviceOptions, Transport } from '@nestjs/microservices';
import { join } from 'path';
import { ValidationPipe } from '@nestjs/common';
import { existsSync } from 'fs';

async function bootstrap() {
  // 1. Tạo HTTP application cho REST APIs với tùy chọn rawBody để xác thực Webhook
  const app = await NestFactory.create(AppModule, { rawBody: true });

  // Kích hoạt Graceful Shutdown
  app.enableShutdownHooks();

  // 2. Kích hoạt Validation toàn cục
  app.useGlobalPipes(
    new ValidationPipe({
      whitelist: true,
      transform: true,
    }),
  );

  // 3. Cấu hình gRPC Microservice
  const protoPath = existsSync(join(__dirname, '../proto/user.proto'))
    ? join(__dirname, '../proto/user.proto')
    : join(__dirname, '../../proto/user.proto');

  app.connectMicroservice<MicroserviceOptions>({
    transport: Transport.GRPC,
    options: {
      url: '0.0.0.0:50058',
      package: 'solavie.user.v1',
      protoPath: protoPath,
    },
  });

  // 4. Khởi chạy microservice
  await app.startAllMicroservices();

  // 5. Lắng nghe HTTP request
  const port = process.env.PORT || 3008;
  await app.listen(port);
  
  console.log(`[User Service] REST API listening on port ${port}`);
  console.log(`[User Service] gRPC Server listening on port 50058`);
}
bootstrap();

import './tracing';
import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { MicroserviceOptions, Transport } from '@nestjs/microservices';
import { join } from 'path';
import { ValidationPipe, Logger } from '@nestjs/common';
import { existsSync } from 'fs';
import { StructuredLoggerService } from './common/observability/structured-logger.service';

async function bootstrap() {
  const loggerService = new StructuredLoggerService();
  // 1. Tạo HTTP application cho REST APIs với tùy chọn rawBody và custom logger
  const app = await NestFactory.create(AppModule, { 
    rawBody: true,
    logger: loggerService,
  });

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
  
  const logger = new Logger('Bootstrap');
  logger.log(`REST API listening on port ${port}`);
  logger.log(`gRPC Server listening on port 50058`);
}
bootstrap();

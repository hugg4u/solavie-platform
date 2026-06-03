import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import * as crypto from 'crypto';

@Injectable()
export class WebhookGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const signature = request.headers['x-webhook-signature'] as string;
    
    if (!signature) {
      throw new UnauthorizedException('Missing X-Webhook-Signature header');
    }

    // Shared secret cấu hình trong .env (mặc định là webhook_shared_secret)
    const secret = process.env.KEYCLOAK_WEBHOOK_SECRET || 'webhook_shared_secret';
    
    // request.rawBody có sẵn nhờ tùy chọn { rawBody: true } trong main.ts
    const rawBody = request.rawBody;
    if (!rawBody) {
      throw new UnauthorizedException('Cannot read raw body of the request');
    }

    const computedSignature = crypto
      .createHmac('sha256', secret)
      .update(rawBody)
      .digest('hex');

    // crypto.timingSafeEqual yêu cầu 2 Buffer cùng độ dài, nếu khác sẽ crash
    if (signature.length !== computedSignature.length) {
      throw new UnauthorizedException('Invalid Webhook signature');
    }

    const isValid = crypto.timingSafeEqual(
      Buffer.from(signature, 'utf-8'),
      Buffer.from(computedSignature, 'utf-8'),
    );

    if (!isValid) {
      throw new UnauthorizedException('Invalid Webhook signature');
    }

    return true;
  }
}

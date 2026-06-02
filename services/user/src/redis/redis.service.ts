import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { createClient, RedisClientType } from 'redis';

@Injectable()
export class RedisService implements OnModuleInit, OnModuleDestroy {
  private client: RedisClientType;

  constructor() {
    const host = process.env.REDIS_HOST || 'redis';
    const port = process.env.REDIS_PORT || '6379';
    this.client = createClient({
      url: `redis://${host}:${port}`,
    });
  }

  async onModuleInit() {
    await this.client.connect();
  }

  async onModuleDestroy() {
    await this.client.disconnect();
  }

  /**
   * Thiết lập giá trị kèm theo thời hạn hết hạn (TTL)
   */
  async setEx(key: string, seconds: number, value: string): Promise<void> {
    await this.client.setEx(key, seconds, value);
  }

  /**
   * Bắn sự kiện lên Redis Pub/Sub channel
   */
  async publish(channel: string, message: string): Promise<void> {
    await this.client.publish(channel, message);
  }

  /**
   * Lấy instance client để thực hiện các thao tác nâng cao
   */
  getClient(): RedisClientType {
    return this.client;
  }
}

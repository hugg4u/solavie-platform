import { Injectable, OnModuleInit, OnModuleDestroy, Logger } from '@nestjs/common';
import { createClient, createCluster } from 'redis';

@Injectable()
export class RedisService implements OnModuleInit, OnModuleDestroy {
  private client: any;
  private readonly logger = new Logger(RedisService.name);

  constructor() {
    // Constructor remains clean
  }

  async onModuleInit() {
    const host = process.env.REDIS_HOST || 'redis';
    const port = process.env.REDIS_PORT || '6379';
    const url = `redis://${host}:${port}`;

    try {
      this.logger.log(`Attempting to connect to Redis Cluster via ${url}...`);
      const cluster = createCluster({
        rootNodes: [{ url }],
        defaults: {
          socket: {
            reconnectStrategy: (retries) => {
              if (retries > 3) {
                return new Error('Redis Cluster connection failed');
              }
              return 1000;
            }
          }
        }
      });

      cluster.on('error', (err) => this.logger.error('Redis Cluster Error:', err));
      await cluster.connect();
      this.client = cluster;
      this.logger.log('Connected to Redis Cluster successfully.');
    } catch (clusterErr: any) {
      this.logger.warn(`Redis Cluster connection failed: ${clusterErr.message}. Falling back to Standalone Redis client.`);
      
      try {
        const client = createClient({ url });
        client.on('error', (err) => this.logger.error('Redis Standalone Error:', err));
        await client.connect();
        this.client = client;
        this.logger.log('Connected to Standalone Redis successfully.');
      } catch (standaloneErr: any) {
        this.logger.error(`Failed to connect to Redis (both Cluster and Standalone): ${standaloneErr.message}`);
        throw standaloneErr;
      }
    }
  }

  async onModuleDestroy() {
    if (this.client) {
      try {
        await this.client.disconnect();
      } catch (err: any) {
        this.logger.error('Error disconnecting Redis client:', err);
      }
    }
  }

  /**
   * Thiết lập giá trị kèm theo thời hạn hết hạn (TTL)
   */
  async setEx(key: string, seconds: number, value: string): Promise<void> {
    if (this.client) {
      await this.client.setEx(key, seconds, value);
    }
  }

  /**
   * Bắn sự kiện lên Redis Pub/Sub channel
   */
  async publish(channel: string, message: string): Promise<void> {
    if (this.client) {
      await this.client.publish(channel, message);
    }
  }

  /**
   * Lấy instance client để thực hiện các thao tác nâng cao
   */
  getClient(): any {
    return this.client;
  }
}

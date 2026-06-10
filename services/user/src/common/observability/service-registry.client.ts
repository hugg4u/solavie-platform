import { Injectable, OnApplicationBootstrap, BeforeApplicationShutdown, Logger } from '@nestjs/common';
import { RedisService } from '../../redis/redis.service';
import * as dgram from 'dgram';
import * as os from 'os';

@Injectable()
export class ServiceRegistryClient implements OnApplicationBootstrap, BeforeApplicationShutdown {
  private readonly logger = new Logger('ServiceRegistryClient');
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private nodeIp: string = '127.0.0.1';
  private nodePort: number = 3008;
  private readonly redisKey = 'registry:service:user';

  constructor(private readonly redisService: RedisService) {
    this.nodePort = parseInt(process.env.PORT || '3008', 10);
  }

  /**
   * Lấy IP nội bộ sử dụng UDP socket ảo
   */
  private async getInternalIp(): Promise<string> {
    try {
      return await new Promise<string>((resolve, reject) => {
        const socket = dgram.createSocket('udp4');
        socket.connect(53, '8.8.8.8', () => {
          const ip = socket.address().address;
          socket.close();
          resolve(ip);
        });
        socket.on('error', (err) => {
          socket.close();
          reject(err);
        });
        
        // Bổ sung timeout 1s để không bị treo
        setTimeout(() => {
          socket.close();
          reject(new Error('UDP socket connect timeout'));
        }, 1000);
      });
    } catch (err: any) {
      this.logger.warn(`Failed to resolve IP via UDP socket: ${err.message}. Falling back to OS network interfaces.`);
      
      const interfaces = os.networkInterfaces();
      for (const name of Object.keys(interfaces)) {
        for (const iface of interfaces[name] || []) {
          if (iface.family === 'IPv4' && !iface.internal) {
            return iface.address;
          }
        }
      }
      return '127.0.0.1';
    }
  }

  /**
   * Kích hoạt khi ứng dụng khởi chạy và lắng nghe port thành công
   */
  async onApplicationBootstrap() {
    this.nodeIp = await this.getInternalIp();
    const nodeValue = `${this.nodeIp}:${this.nodePort}`;
    const nodeKey = `${this.redisKey}:node:${nodeValue}`;

    try {
      const client = this.redisService.getClient();
      if (!client) {
        throw new Error('Redis client is not initialized');
      }

      // 1. Đăng ký node vào Set
      await client.sAdd(this.redisKey, nodeValue);

      // 2. Tạo khóa sống có TTL 15 giây
      await client.setEx(nodeKey, 15, 'alive');

      // 3. Log JSON theo đặc tả
      this.logger.log({
        message: 'Service node registration completed',
        action: 'register',
        node_ip: this.nodeIp,
        node_port: this.nodePort,
        status: 'success',
        context: {
          redis_key: this.redisKey,
        },
      });

      // 4. Bắt đầu luồng gửi Heartbeat mỗi 5 giây
      this.heartbeatInterval = setInterval(async () => {
        try {
          await client.setEx(nodeKey, 15, 'alive');
          await client.sAdd(this.redisKey, nodeValue);
        } catch (hbErr: any) {
          this.logger.error({
            message: `Heartbeat failed: ${hbErr.message}`,
            action: 'heartbeat',
            node_ip: this.nodeIp,
            node_port: this.nodePort,
            status: 'error',
            context: {
              redis_key: this.redisKey,
            },
          });
        }
      }, 5000);

    } catch (err: any) {
      this.logger.error({
        message: `Failed to register service node: ${err.message}`,
        action: 'register',
        node_ip: this.nodeIp,
        node_port: this.nodePort,
        status: 'error',
        context: {
          redis_key: this.redisKey,
        },
      });
    }
  }

  /**
   * Kích hoạt trước khi ứng dụng tắt (Graceful Shutdown)
   */
  async beforeApplicationShutdown() {
    // 1. Dọn dẹp interval
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    const nodeValue = `${this.nodeIp}:${this.nodePort}`;
    const nodeKey = `${this.redisKey}:node:${nodeValue}`;

    try {
      const client = this.redisService.getClient();
      if (client) {
        // 2. Xóa node khỏi Set
        await client.sRem(this.redisKey, nodeValue);

        // 3. Xóa khóa sống
        await client.del(nodeKey);
      }

      // 4. Log JSON hủy đăng ký thành công
      this.logger.log({
        message: 'Service node deregistration completed',
        action: 'deregister',
        node_ip: this.nodeIp,
        node_port: this.nodePort,
        status: 'success',
        context: {
          redis_key: this.redisKey,
        },
      });

    } catch (err: any) {
      this.logger.error({
        message: `Failed to deregister service node: ${err.message}`,
        action: 'deregister',
        node_ip: this.nodeIp,
        node_port: this.nodePort,
        status: 'error',
        context: {
          redis_key: this.redisKey,
        },
      });
    }
  }
}

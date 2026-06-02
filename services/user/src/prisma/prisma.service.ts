import { Injectable, OnModuleInit, OnModuleDestroy } from '@nestjs/common';
import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { Pool } from 'pg';
import { getTenantId } from '../common/context/tenant-context';

@Injectable()
export class PrismaService extends PrismaClient implements OnModuleInit, OnModuleDestroy {
  private readonly pool: Pool;

  constructor() {
    // URL kết nối cơ sở dữ liệu lấy từ biến môi trường
    const connectionString = process.env.DATABASE_URL;
    const pool = new Pool({ connectionString });
    const adapter = new PrismaPg(pool);
    
    super({
      adapter,
      log: ['error', 'warn'] as any[],
    });
    
    this.pool = pool;
  }

  async onModuleInit() {
    await this.$connect();
  }

  async onModuleDestroy() {
    await this.$disconnect();
    await this.pool.end();
  }

  /**
   * Chạy các truy vấn database trong phạm vi transaction có áp dụng Row-Level Security (RLS)
   * của Tenant hiện tại lấy từ AsyncLocalStorage.
   */
  async runInTenantContext<T>(
    callback: (tx: any) => Promise<T>,
  ): Promise<T> {
    const tenantId = getTenantId();
    
    // Nếu không có tenant_id trong context (ví dụ: webhook hệ thống hoặc job đặc quyền),
    // chúng ta sẽ chạy truy vấn bình thường (không RLS).
    if (!tenantId) {
      return callback(this);
    }

    // Kiểm tra định dạng UUID của tenantId để ngăn chặn lỗi SQL Injection
    const uuidRegex = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
    if (!uuidRegex.test(tenantId)) {
      throw new Error('Invalid Tenant ID format');
    }

    // Thực thi trong một Transaction để SET LOCAL có hiệu lực và tự động giải phóng sau đó
    return this.$transaction(async (tx) => {
      await tx.$executeRawUnsafe(`SET LOCAL app.current_tenant_id = '${tenantId}'`);
      return callback(tx);
    });
  }
}

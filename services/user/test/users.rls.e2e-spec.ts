import { PrismaClient } from '@prisma/client';
import { PrismaPg } from '@prisma/adapter-pg';
import { Pool } from 'pg';

describe('User Service Row-Level Security (RLS) Integration Test', () => {
  let prisma: PrismaClient;
  let regularPool: Pool;

  const tenantA = 'a0000000-0000-0000-0000-00000000000a';
  const tenantB = 'b0000000-0000-0000-0000-00000000000b';

  const userAId = 'a1111111-1111-1111-1111-11111111111a';
  const userBId = 'b1111111-1111-1111-1111-11111111111b';

  beforeAll(async () => {
    // 1. Cấu hình kết nối bằng Superuser để dọn dẹp và seed dữ liệu mẫu
    const superuserUrl = process.env.DATABASE_URL?.replace(
      'solavie_user:solavie_user_password',
      'postgres:postgres_master_password',
    ) || 'postgresql://postgres:postgres_master_password@localhost:5433/solavie_user_db?schema=public';

    const superuserPool = new Pool({ connectionString: superuserUrl });
    const superuserAdapter = new PrismaPg(superuserPool);
    const superuserPrisma = new PrismaClient({ adapter: superuserAdapter });
    
    await superuserPrisma.$connect();
    await superuserPrisma.$executeRawUnsafe(`TRUNCATE TABLE users CASCADE;`);

    // Seed User A cho Tenant A
    await superuserPrisma.user.create({
      data: {
        id: userAId,
        tenantId: tenantA,
        status: 'ACTIVE',
        phoneNumber: '0901111111',
        preferences: { create: { theme: 'dark', language: 'vi' } },
      },
    });

    // Seed User B cho Tenant B
    await superuserPrisma.user.create({
      data: {
        id: userBId,
        tenantId: tenantB,
        status: 'ACTIVE',
        phoneNumber: '0902222222',
        preferences: { create: { theme: 'light', language: 'en' } },
      },
    });

    await superuserPrisma.$disconnect();
    await superuserPool.end();

    // 2. Khởi tạo Prisma client thường (kết nối bằng solavie_user chịu ảnh hưởng RLS)
    const regularUrl = process.env.DATABASE_URL || 'postgresql://solavie_user:solavie_user_password@localhost:5433/solavie_user_db?schema=public';
    regularPool = new Pool({ connectionString: regularUrl });
    const regularAdapter = new PrismaPg(regularPool);
    prisma = new PrismaClient({ adapter: regularAdapter });
    await prisma.$connect();
  });

  afterAll(async () => {
    // Dọn dẹp dữ liệu sạch sẽ bằng Superuser sau khi test xong
    const superuserUrl = process.env.DATABASE_URL?.replace(
      'solavie_user:solavie_user_password',
      'postgres:postgres_master_password',
    ) || 'postgresql://postgres:postgres_master_password@localhost:5433/solavie_user_db?schema=public';

    const superuserPool = new Pool({ connectionString: superuserUrl });
    const superuserAdapter = new PrismaPg(superuserPool);
    const superuserPrisma = new PrismaClient({ adapter: superuserAdapter });
    
    await superuserPrisma.$connect();
    await superuserPrisma.$executeRawUnsafe(`TRUNCATE TABLE users CASCADE;`);
    await superuserPrisma.$disconnect();
    await superuserPool.end();

    await prisma.$disconnect();
    await regularPool.end();
  });

  it('should only return Tenant A data when app.current_tenant_id is set to Tenant A', async () => {
    await prisma.$transaction(async (tx) => {
      // Thiết lập context cho Tenant A
      await tx.$executeRawUnsafe(`SET LOCAL app.current_tenant_id = '${tenantA}';`);

      // Tìm User A (phải thấy)
      const userA = await tx.user.findUnique({ where: { id: userAId } });
      expect(userA).toBeDefined();
      expect(userA?.id).toBe(userAId);
      expect(userA?.tenantId).toBe(tenantA);

      // Tìm User B (phải KHÔNG thấy - bị RLS chặn)
      const userB = await tx.user.findUnique({ where: { id: userBId } });
      expect(userB).toBeNull();
    });
  });

  it('should only return Tenant B data when app.current_tenant_id is set to Tenant B', async () => {
    await prisma.$transaction(async (tx) => {
      // Thiết lập context cho Tenant B
      await tx.$executeRawUnsafe(`SET LOCAL app.current_tenant_id = '${tenantB}';`);

      // Tìm User B (phải thấy)
      const userB = await tx.user.findUnique({ where: { id: userBId } });
      expect(userB).toBeDefined();
      expect(userB?.id).toBe(userBId);
      expect(userB?.tenantId).toBe(tenantB);

      // Tìm User A (phải KHÔNG thấy - bị RLS chặn)
      const userA = await tx.user.findUnique({ where: { id: userAId } });
      expect(userA).toBeNull();
    });
  });
});

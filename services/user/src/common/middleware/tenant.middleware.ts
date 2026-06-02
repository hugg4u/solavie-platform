import { Injectable, NestMiddleware } from '@nestjs/common';
import { Request, Response, NextFunction } from 'express';
import { tenantContextStorage } from '../context/tenant-context';

@Injectable()
export class TenantMiddleware implements NestMiddleware {
  use(req: Request, res: Response, next: NextFunction) {
    const tenantId = req.header('x-tenant-id');
    const userId = req.header('x-user-id');

    // Chạy callback tiếp theo trong phạm vi context được thiết lập
    tenantContextStorage.run({ tenantId, userId }, () => {
      next();
    });
  }
}

import { Injectable, NestInterceptor, ExecutionContext, CallHandler } from '@nestjs/common';
import { Observable, throwError } from 'rxjs';
import { tap, catchError } from 'rxjs/operators';
import { MetricsService } from './metrics.service';
import { Response, Request } from 'express';
import { getTenantId } from '../../context/tenant-context';

@Injectable()
export class MetricsInterceptor implements NestInterceptor {
  constructor(private readonly metricsService: MetricsService) {}

  intercept(context: ExecutionContext, next: CallHandler): Observable<any> {
    // Chỉ đo lường cho HTTP requests, bỏ qua gRPC
    if (context.getType() !== 'http') {
      return next.handle();
    }

    const httpContext = context.switchToHttp();
    const request = httpContext.getRequest<Request>();
    const response = httpContext.getResponse<Response>();

    const start = process.hrtime();

    const record = (statusCode: number) => {
      const diff = process.hrtime(start);
      const durationSeconds = diff[0] + diff[1] / 1e9;
      const method = request.method;
      // Tránh việc ghi nhận các ID thay đổi làm nổ dữ liệu (Path parameter explosion)
      const route = request.route?.path || request.path;
      const tenantId = getTenantId() || 'unknown';
      this.metricsService.recordRequest(method, route, statusCode, durationSeconds, tenantId);
    };

    return next.handle().pipe(
      tap(() => {
        record(response.statusCode);
      }),
      catchError((err) => {
        const statusCode = err.status || err.statusCode || 500;
        record(statusCode);
        return throwError(() => err);
      }),
    );
  }
}

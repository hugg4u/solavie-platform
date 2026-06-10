import { Injectable } from '@nestjs/common';
import { Counter, Histogram, Registry, collectDefaultMetrics } from 'prom-client';

@Injectable()
export class MetricsService {
  private readonly registry: Registry;

  public readonly httpRequestsTotal: Counter<string>;
  public readonly httpRequestDuration: Histogram<string>;
  public readonly keycloakSyncOperations: Counter<string>;
  public readonly securitySignatureFailures: Counter<string>;
  public readonly securityPermissionDenied: Counter<string>;

  constructor() {
    this.registry = new Registry();

    // Thu thập các metrics mặc định của Node.js (CPU, Memory, GC, v.v.)
    collectDefaultMetrics({ register: this.registry, prefix: 'user_service_' });

    // 1. Thống kê HTTP request
    this.httpRequestsTotal = new Counter({
      name: 'user_service_http_requests_total',
      help: 'Total HTTP requests in User Service',
      labelNames: ['method', 'handler', 'status_code', 'tenant_id'],
      registers: [this.registry],
    });

    this.httpRequestDuration = new Histogram({
      name: 'user_service_http_request_duration_seconds',
      help: 'HTTP request latency distribution',
      labelNames: ['method', 'handler'],
      buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
      registers: [this.registry],
    });

    // 2. Thống kê đồng bộ Keycloak
    this.keycloakSyncOperations = new Counter({
      name: 'user_service_keycloak_sync_total',
      help: 'Total sync operations with Keycloak',
      labelNames: ['direction', 'operation', 'status'], // direction: IN, OUT; status: success, error
      registers: [this.registry],
    });

    // 3. Thống kê Bảo mật & Zero-Trust
    this.securitySignatureFailures = new Counter({
      name: 'user_service_security_signature_failures_total',
      help: 'Total HMAC signature validation failures on X-Permissions-Signature',
      labelNames: ['tenant_id'],
      registers: [this.registry],
    });

    this.securityPermissionDenied = new Counter({
      name: 'user_service_security_permission_denied_total',
      help: 'Total permission denied decisions at downstream guard',
      labelNames: ['tenant_id', 'required_permission'],
      registers: [this.registry],
    });
  }

  /**
   * Ghi nhận HTTP Request
   */
  recordRequest(method: string, route: string, status: number, durationSeconds: number, tenantId: string = 'unknown') {
    this.httpRequestsTotal.inc({
      method,
      handler: route,
      status_code: status.toString(),
      tenant_id: tenantId || 'unknown',
    });

    this.httpRequestDuration.observe(
      {
        method,
        handler: route,
      },
      durationSeconds,
    );
  }

  /**
   * Ghi nhận Keycloak Sync Operation
   */
  recordKeycloakSync(direction: 'IN' | 'OUT', operation: string, status: 'success' | 'error') {
    this.keycloakSyncOperations.inc({
      direction,
      operation,
      status,
    });
  }

  /**
   * Ghi nhận lỗi Signature Mismatch
   */
  recordSignatureFailure(tenantId: string = 'unknown') {
    this.securitySignatureFailures.inc({
      tenant_id: tenantId || 'unknown',
    });
  }

  /**
   * Ghi nhận lỗi Permission Denied
   */
  recordPermissionDenied(tenantId: string = 'unknown', requiredPermission: string) {
    this.securityPermissionDenied.inc({
      tenant_id: tenantId || 'unknown',
      required_permission: requiredPermission,
    });
  }

  /**
   * Trả về định dạng metric chuẩn Prometheus
   */
  async getMetricsResponse(): Promise<string> {
    return this.registry.metrics();
  }
}

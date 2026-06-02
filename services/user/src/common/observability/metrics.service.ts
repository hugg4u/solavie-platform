import { Injectable } from '@nestjs/common';

@Injectable()
export class MetricsService {
  private requestCounter = new Map<string, number>(); // key: `method|route|status`
  private durationSum = new Map<string, number>(); // key: `method|route`
  private durationCount = new Map<string, number>(); // key: `method|route`
  private durationBuckets = new Map<string, Map<number, number>>(); // key: `method|route`, inner key: le (bucket limit)

  // Standard latency buckets in seconds
  private readonly buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10];

  recordRequest(method: string, route: string, status: number, durationSeconds: number) {
    // 1. Record HTTP requests count
    const counterKey = `${method}|${route}|${status}`;
    const currentCount = this.requestCounter.get(counterKey) || 0;
    this.requestCounter.set(counterKey, currentCount + 1);

    // 2. Record HTTP request duration sum & count
    const durationKey = `${method}|${route}`;
    const currentSum = this.durationSum.get(durationKey) || 0;
    this.durationSum.set(durationKey, currentSum + durationSeconds);

    const currentDurCount = this.durationCount.get(durationKey) || 0;
    this.durationCount.set(durationKey, currentDurCount + 1);

    // 3. Record HTTP request duration buckets
    if (!this.durationBuckets.has(durationKey)) {
      const initialMap = new Map<number, number>();
      for (const le of this.buckets) {
        initialMap.set(le, 0);
      }
      initialMap.set(Infinity, 0);
      this.durationBuckets.set(durationKey, initialMap);
    }
    
    const routeBuckets = this.durationBuckets.get(durationKey)!;
    
    for (const le of this.buckets) {
      if (durationSeconds <= le) {
        const count = routeBuckets.get(le) || 0;
        routeBuckets.set(le, count + 1);
      }
    }
    
    // Inf bucket
    const infCount = routeBuckets.get(Infinity) || 0;
    routeBuckets.set(Infinity, infCount + 1);
  }

  getMetricsResponse(): string {
    let output = '';

    // 1. Process Uptime Metric
    output += '# HELP process_uptime_seconds Uptime of the service in seconds.\n';
    output += '# TYPE process_uptime_seconds gauge\n';
    output += `process_uptime_seconds ${process.uptime().toFixed(2)}\n\n`;

    // 2. HTTP Requests Total Counter Metric
    output += '# HELP http_requests_total Total number of HTTP requests.\n';
    output += '# TYPE http_requests_total counter\n';
    for (const [key, value] of this.requestCounter.entries()) {
      const [method, route, status] = key.split('|');
      output += `http_requests_total{method="${method}",route="${route}",status="${status}"} ${value}\n`;
    }
    output += '\n';

    // 3. HTTP Request Duration Histogram Metrics
    output += '# HELP http_request_duration_seconds Response latency in seconds.\n';
    output += '# TYPE http_request_duration_seconds histogram\n';
    
    for (const durationKey of this.durationCount.keys()) {
      const [method, route] = durationKey.split('|');
      const routeBuckets = this.durationBuckets.get(durationKey)!;
      
      // Print buckets
      for (const le of this.buckets) {
        const count = routeBuckets.get(le) || 0;
        output += `http_request_duration_seconds_bucket{method="${method}",route="${route}",le="${le}"} ${count}\n`;
      }
      // Inf bucket
      const infCount = routeBuckets.get(Infinity) || 0;
      output += `http_request_duration_seconds_bucket{method="${method}",route="${route}",le="+Inf"} ${infCount}\n`;
      
      // Sum and Count
      const sum = this.durationSum.get(durationKey) || 0;
      const count = this.durationCount.get(durationKey) || 0;
      output += `http_request_duration_seconds_sum{method="${method}",route="${route}"} ${sum.toFixed(6)}\n`;
      output += `http_request_duration_seconds_count{method="${method}",route="${route}"} ${count}\n`;
    }

    return output;
  }
}

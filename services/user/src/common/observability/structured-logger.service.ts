import { Injectable, LoggerService } from '@nestjs/common';
import pino from 'pino';
import { trace, context as otelContext } from '@opentelemetry/api';
import { getTenantId } from '../context/tenant-context';

export function maskPhoneNumberString(text: string): string {
  if (typeof text !== 'string') return text;
  // Tìm chuỗi số (có thể có dấu + ở đầu) dài từ 9 đến 13 ký tự số độc lập
  return text.replace(/(?<!\d)(\+\d{2}|\d{3})(\d{3,7})(\d{3})(?!\d)/g, (match, p1, p2, p3) => {
    return `${p1}${'*'.repeat(p2.length)}${p3}`;
  });
}

export function maskObject(obj: any): any {
  if (!obj || typeof obj !== 'object') {
    if (typeof obj === 'string') {
      return maskPhoneNumberString(obj);
    }
    return obj;
  }
  
  if (Array.isArray(obj)) {
    return obj.map(item => maskObject(item));
  }
  
  const maskedObj: any = {};
  for (const key of Object.keys(obj)) {
    const val = obj[key];
    const lowerKey = key.toLowerCase();
    // Che giấu số điện thoại nếu key có tên chứa từ nhạy cảm
    if (lowerKey.includes('phone') || lowerKey.includes('sdt') || lowerKey.includes('telephone')) {
      if (typeof val === 'string') {
        maskedObj[key] = maskPhoneNumberString(val);
      } else {
        maskedObj[key] = val;
      }
    } else {
      maskedObj[key] = maskObject(val);
    }
  }
  return maskedObj;
}

@Injectable()
export class StructuredLoggerService implements LoggerService {
  private readonly logger: pino.Logger;

  constructor() {
    const isProduction = 
      process.env.NODE_ENV === 'production' || 
      process.env.ENVIRONMENT === 'production';
    const pinoOptions: pino.LoggerOptions = {
      messageKey: 'message',
      timestamp: () => `,"timestamp":"${new Date().toISOString()}"`,
      formatters: {
        level: (label) => {
          return { level: label };
        },
      },
      base: {
        service: 'user-service',
      },
    };

    if (!isProduction) {
      pinoOptions.transport = {
        target: 'pino-pretty',
        options: {
          colorize: true,
          translateTime: 'SYS:standard',
          ignore: 'pid,hostname',
        },
      };
    }

    this.logger = pino(pinoOptions);
  }

  private getContextData(contextName?: string) {
    const activeSpan = trace.getSpan(otelContext.active());
    let traceId: string | undefined;
    let spanId: string | undefined;

    if (activeSpan) {
      const spanContext = activeSpan.spanContext();
      traceId = spanContext.traceId;
      spanId = spanContext.spanId;
    }

    const tenantId = getTenantId();

    return {
      trace_id: traceId,
      span_id: spanId,
      tenant_id: tenantId,
      context_name: contextName,
    };
  }

  log(message: any, context?: string) {
    const contextData = this.getContextData(context);
    const maskedMessage = typeof message === 'string' ? maskPhoneNumberString(message) : maskObject(message);
    
    if (typeof maskedMessage === 'object' && maskedMessage !== null) {
      this.logger.info({ ...contextData, ...maskedMessage });
    } else {
      this.logger.info({ ...contextData }, maskedMessage);
    }
  }

  error(message: any, traceStack?: string, context?: string) {
    const contextData = this.getContextData(context);
    const maskedMessage = typeof message === 'string' ? maskPhoneNumberString(message) : maskObject(message);
    
    const errData: any = { ...contextData };
    if (traceStack) {
      errData.stack = traceStack;
    }

    if (typeof maskedMessage === 'object' && maskedMessage !== null) {
      this.logger.error({ ...errData, ...maskedMessage });
    } else {
      this.logger.error(errData, maskedMessage);
    }
  }

  warn(message: any, context?: string) {
    const contextData = this.getContextData(context);
    const maskedMessage = typeof message === 'string' ? maskPhoneNumberString(message) : maskObject(message);
    
    if (typeof maskedMessage === 'object' && maskedMessage !== null) {
      this.logger.warn({ ...contextData, ...maskedMessage });
    } else {
      this.logger.warn({ ...contextData }, maskedMessage);
    }
  }

  debug(message: any, context?: string) {
    const contextData = this.getContextData(context);
    const maskedMessage = typeof message === 'string' ? maskPhoneNumberString(message) : maskObject(message);
    
    if (typeof maskedMessage === 'object' && maskedMessage !== null) {
      this.logger.debug({ ...contextData, ...maskedMessage });
    } else {
      this.logger.debug({ ...contextData }, maskedMessage);
    }
  }

  verbose(message: any, context?: string) {
    const contextData = this.getContextData(context);
    const maskedMessage = typeof message === 'string' ? maskPhoneNumberString(message) : maskObject(message);
    
    if (typeof maskedMessage === 'object' && maskedMessage !== null) {
      this.logger.trace({ ...contextData, ...maskedMessage });
    } else {
      this.logger.trace({ ...contextData }, maskedMessage);
    }
  }
}

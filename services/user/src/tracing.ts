import { NodeSDK } from '@opentelemetry/sdk-node';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';
import { OTLPTraceExporter } from '@opentelemetry/exporter-trace-otlp-grpc';

const otelEndpoint = process.env.OTEL_EXPORTER_OTLP_ENDPOINT || 'http://otel-collector:4317';
const sdkEnabled = process.env.OTEL_SDK_DISABLED !== 'true';

if (sdkEnabled) {
  const sdk = new NodeSDK({
    traceExporter: new OTLPTraceExporter({
      url: otelEndpoint,
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        // Vô hiệu hóa fs instrumentation để tránh spam trace spans quá mức
        '@opentelemetry/instrumentation-fs': {
          enabled: false,
        },
      }),
    ],
  });

  sdk.start();
  console.log(`[OpenTelemetry] Tracing initialized exporting to ${otelEndpoint}`);

  process.on('SIGTERM', () => {
    sdk.shutdown()
      .then(() => console.log('[OpenTelemetry] Tracing terminated successfully'))
      .catch((error) => console.error('[OpenTelemetry] Error terminating tracing', error));
  });
} else {
  console.log('[OpenTelemetry] SDK is disabled via OTEL_SDK_DISABLED env.');
}

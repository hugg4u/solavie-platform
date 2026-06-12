local typedefs = require "kong.db.schema.typedefs"

return {
  name = "dynamic-policy",
  fields = {
    {
      config = {
        type = "record",
        fields = {
          { redis_host = { type = "string", default = "redis" } },
          { redis_port = { type = "number", default = 6379 } },
          { tenant_config_internal_url = { type = "string", default = "http://tenant-config:3006" } },
          { default_tenant_id = { type = "string", default = "tenant-test-uuid" } },
          { default_rate_limit_minute = { type = "number", default = 200 } },
          { default_rate_limit_hour = { type = "number", default = 5000 } },
          { gateway_signing_secret = { type = "string", default = "default-gateway-signing-secret-key-change-me-in-production" } },
        },
      },
    },
  },
}


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
        },
      },
    },
  },
}

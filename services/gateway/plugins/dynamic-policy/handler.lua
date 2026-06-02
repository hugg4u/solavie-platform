local cjson = require "cjson"
local redis = require "resty.redis"

-- Route scopes are resolved dynamically from Kong Route tags (e.g. tag "scope:ai-core")

local DynamicPolicyHandler = {
  PRIORITY = 2000,
  VERSION = "0.1.0",
}

local function close_redis(red, ok)
  if ok and red then
      red:set_keepalive(10000, 100)
  end
end

function DynamicPolicyHandler:access(conf)
  local path = kong.request.get_path()
  if string.find(path, "^/webhooks") or string.find(path, "^/health") or string.find(path, "^/ready") then
      return
  end

  local method = kong.request.get_method()
  if method == "OPTIONS" then
      local origin = kong.request.get_header("Origin") or "*"
      kong.response.set_header("Access-Control-Allow-Origin", origin)
      kong.response.set_header("Access-Control-Allow-Credentials", "true")
      kong.response.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tenant-ID")
      kong.response.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
      return kong.response.exit(204)
  end

  local tenant_id = kong.request.get_header("X-Tenant-ID")
  local jti = nil
  local claims = nil

  local auth_header = kong.request.get_header("Authorization")
  if auth_header and string.sub(auth_header, 1, 7):lower() == "bearer " then
      local token = string.sub(auth_header, 8)

      local parts = {}
      for part in string.gmatch(token, "[^%.]+") do
          table.insert(parts, part)
      end
      if #parts >= 2 then
          local payload_b64 = parts[2]
          payload_b64 = payload_b64:gsub("-", "+"):gsub("_", "/")
          local rem = #payload_b64 % 4
          if rem > 0 then
              payload_b64 = payload_b64 .. string.rep("=", 4 - rem)
          end
          
          local decoded = ngx.decode_base64(payload_b64)
          if decoded then
              local success, parsed_claims = pcall(function() return cjson.decode(decoded) end)
              if success and parsed_claims then
                  claims = parsed_claims
                  if not tenant_id and claims.tenant_id then
                      tenant_id = claims.tenant_id
                  end
                  if claims.jti then
                      jti = claims.jti
                  end
                  kong.log.notice("Parsed JTI: ", tostring(jti), " Tenant ID: ", tostring(tenant_id))
              else
                  kong.log.err("Failed to decode JSON payload: ", tostring(success))
              end

          else
              kong.log.err("Failed to decode base64 payload: ", tostring(payload_b64))
          end
      else
          kong.log.err("Invalid JWT token format, parts count: ", #parts)
      end
  else
      kong.log.notice("No Bearer token found in Authorization header")
  end

  if not tenant_id then
      tenant_id = "tenant-test-uuid"
  end

  kong.service.request.set_header("X-Tenant-ID", tenant_id)

  -- Scope Validation via Route Tags
  local required_scope = nil
  local route = kong.router.get_route()
  if route and route.tags then
      for _, tag in ipairs(route.tags) do
          if string.sub(tag, 1, 6) == "scope:" then
              required_scope = string.sub(tag, 7)
              break
          end
      end
  end

  if required_scope then
      local has_scope = false
      if claims and claims.scope then
          for s in string.gmatch(claims.scope, "%S+") do
              if s == required_scope then
                  has_scope = true
                  break
              end
          end
      end
      if not has_scope then
          kong.log.warn("Missing required scope '", required_scope, "' for path: ", path)
          return kong.response.exit(403, { message = "Forbidden: missing required scope" })
      end
  end

  local red = redis:new()
  red:set_timeouts(1000, 1000, 1000)
  local ok, err = red:connect(conf.redis_host, conf.redis_port)
  if not ok then
      kong.log.err("Failed to connect to Redis: ", tostring(err))
  end
  
  if ok and jti then
      local redis_key = "blacklist:jti:" .. jti
      local is_blacklisted, err = red:get(redis_key)
      kong.log.notice("Checking Redis key: ", redis_key, " Result: ", tostring(is_blacklisted))
      if is_blacklisted and is_blacklisted ~= ngx.null then
          close_redis(red, ok)
          kong.log.warn("Blocking request due to blacklisted JTI: ", jti)
          return kong.response.exit(401, { message = "Token has been revoked" })
      end
  end

  local config = nil
  if ok then
      local res, err = red:get("tenant:" .. tenant_id .. ":config:security_comments_notif")
      if not res or res == ngx.null then
          res, err = red:get(tenant_id .. ":config:security_comments_notif")
      end
      if res and res ~= ngx.null then
          local success, parsed = pcall(function() return cjson.decode(res) end)
          if success then
              config = parsed
          end
      end
  end

  local limit_min = config and config.gateway_rate_limit_minute or 200
  local limit_hour = config and config.gateway_rate_limit_hour or 5000
  local allowed_origins = config and config.allowed_cors_origins or {"*"}

  local origin = kong.request.get_header("Origin")
  local origin_allowed = false

  if origin then
      for _, allowed in ipairs(allowed_origins) do
          if allowed == "*" or allowed == origin then
              origin_allowed = true
              break
          end
      end
      
      if not origin_allowed then
          close_redis(red, ok)
          return kong.response.exit(403, { message = "CORS origin not allowed" })
      end
      
      kong.response.set_header("Access-Control-Allow-Origin", origin)
      kong.response.set_header("Access-Control-Allow-Credentials", "true")
      kong.response.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tenant-ID")
      kong.response.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
      
      local method = kong.request.get_method()
      if method == "OPTIONS" then
          close_redis(red, ok)
          return kong.response.exit(204)
      end
  else
      kong.response.set_header("Access-Control-Allow-Origin", "*")
  end

  if ok then
      local current_time = os.time()
      local min_bucket = math.floor(current_time / 60)
      local hour_bucket = math.floor(current_time / 3600)
      
      local key_min = "rate:" .. tenant_id .. ":min:" .. min_bucket
      local key_hour = "rate:" .. tenant_id .. ":hour:" .. hour_bucket
      
      local current_min, err_min = red:incr(key_min)
      if current_min and current_min == 1 then
          red:expire(key_min, 60)
      end
      
      local current_hour, err_hour = red:incr(key_hour)
      if current_hour and current_hour == 1 then
          red:expire(key_hour, 3600)
      end
      
      close_redis(red, ok)
      
      if current_min then
          kong.response.set_header("X-RateLimit-Limit-Minute", limit_min)
          kong.response.set_header("X-RateLimit-Remaining-Minute", math.max(0, limit_min - current_min))
          
          if current_min > limit_min or (current_hour and current_hour > limit_hour) then
              return kong.response.exit(429, { message = "API rate limit exceeded" })
          end
      end
  else
      close_redis(red, ok)
  end
end

return DynamicPolicyHandler

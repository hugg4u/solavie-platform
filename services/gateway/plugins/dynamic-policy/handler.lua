local cjson = require "cjson"
local redis = require "resty.redis"
local http_ok, http = pcall(require, "resty.http")
local hmac = require "resty.hmac"

-- Worker-level in-memory cache for role permissions
local local_cache = {}

local DynamicPolicyHandler = {
  PRIORITY = 2000,
  VERSION = "0.2.0",
}

local function close_redis(red, ok)
  if ok and red then
      red:set_keepalive(10000, 100)
  end
end

local function to_hex(str)
  return (str:gsub('.', function (c)
      return string.format('%02x', string.byte(c))
  end))
end

local function get_circuit_state()
  local circuit = ngx.shared.circuit_state
  if not circuit then
      return "CLOSED"
  end
  local state = circuit:get("state") or "CLOSED"
  local last_failure = circuit:get("last_failure_time") or 0
  
  if state == "OPEN" then
      if os.time() - last_failure > 10 then -- 10 seconds cooldown
          circuit:set("state", "HALF-OPEN")
          state = "HALF-OPEN"
          kong.log.notice("Circuit Breaker: state transitioning to HALF-OPEN")
      end
  end
  return state
end

local function record_success()
  local circuit = ngx.shared.circuit_state
  if circuit then
      circuit:set("state", "CLOSED")
      circuit:set("failures", 0)
      kong.log.notice("Circuit Breaker: request succeeded, state reset to CLOSED")
  end
end

local function record_failure()
  local circuit = ngx.shared.circuit_state
  if circuit then
      local failures = (circuit:get("failures") or 0) + 1
      circuit:set("failures", failures)
      circuit:set("last_failure_time", os.time())
      kong.log.warn("Circuit Breaker: failure recorded, failures=", failures)
      if failures >= 3 then
          circuit:set("state", "OPEN")
          kong.log.alert("Circuit Breaker: failure threshold reached, state set to OPEN")
      end
  end
end

local function get_permissions_for_role(tenant_id, role, red, redis_ok, conf)
  local cache_key = tenant_id .. ":" .. role
  
  -- 1. Check L1 Cache (ngx.shared.perm_cache)
  local perm_cache = ngx.shared.perm_cache
  if perm_cache then
      local cached_val = perm_cache:get(cache_key)
      if cached_val then
          local success, parsed = pcall(cjson.decode, cached_val)
          if success and parsed then
              return parsed
          end
      end
  end

  -- 2. Check Redis Cache
  if redis_ok then
      local redis_key = "tenant:" .. tenant_id .. ":role:" .. role .. ":permissions"
      local res, err = red:get(redis_key)
      if res and res ~= ngx.null then
          local success, parsed = pcall(cjson.decode, res)
          if success and parsed then
              if perm_cache then
                  local success_enc, encoded = pcall(cjson.encode, parsed)
                  if success_enc and encoded then
                      perm_cache:set(cache_key, encoded, 300) -- Cache 5 mins in L1
                  end
              end
              return parsed
          end
      end
  end

  -- 3. API Fallback to Tenant Config Service with Circuit Breaker
  local state = get_circuit_state()
  if state == "OPEN" then
      kong.log.warn("Circuit Breaker: state is OPEN, skipping API fallback call to Tenant Config Service")
      return nil
  end

  if http_ok then
      local httpc = http.new()
      httpc:set_timeout(1000) -- 1s timeout
      
      local res, err = httpc:request_uri("http://tenant-config:3006/api/v1/config/tenants/" .. tenant_id .. "/roles/permissions", {
          method = "GET",
          query = { roles = role },
          headers = {
              ["Content-Type"] = "application/json",
              ["X-Tenant-ID"] = tenant_id
          }
      })
      
      if res then
          if res.status == 200 then
              record_success()
              local success, parsed = pcall(cjson.decode, res.body)
              if success and parsed then
                  -- Save back to Redis cache (L2) if possible
                  if redis_ok then
                      local redis_key = "tenant:" .. tenant_id .. ":role:" .. role .. ":permissions"
                      red:setex(redis_key, 3600, res.body) -- Cache 1 hour in Redis
                  end
                  
                  if perm_cache then
                      local success_enc, encoded = pcall(cjson.encode, parsed)
                      if success_enc and encoded then
                          perm_cache:set(cache_key, encoded, 300) -- Cache 5 mins in L1
                      end
                  end
                  return parsed
              end
          else
              record_failure()
          end
      else
          record_failure()
      end
  end

  return nil
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
      kong.response.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tenant-ID, X-User-Permissions, X-Permissions-Signature")
      kong.response.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
      return kong.response.exit(204)
  end

  local tenant_id = kong.request.get_header("X-Tenant-ID")
  local jti = nil
  local claims = nil
  local user_id = "anonymous"

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
                  if claims.organization then
                      if type(claims.organization) == "table" then
                          tenant_id = claims.organization[1]
                      elseif type(claims.organization) == "string" then
                          tenant_id = claims.organization
                      end
                  end
                  if claims.jti then
                      jti = claims.jti
                  end
                  if claims.sub then
                      user_id = claims.sub
                  end
                  kong.log.notice("Parsed JTI: ", tostring(jti), " Tenant ID: ", tostring(tenant_id), " User ID: ", tostring(user_id))
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

  -- Connect to Redis
  local red = redis:new()
  red:set_timeouts(1000, 1000, 1000)
  local ok, err = red:connect(conf.redis_host, conf.redis_port)
  if not ok then
      kong.log.err("Failed to connect to Redis: ", tostring(err))
  end

  -- Resolve Permissions (Dynamic RBAC)
  local user_permissions = ""
  if claims then
      local roles = {}
      if claims.realm_access and claims.realm_access.roles then
          roles = claims.realm_access.roles
      elseif claims.roles then
          roles = claims.roles
      end

      local permissions_set = {}
      local has_wildcard = false
      local resolved_any = false

      -- 1. Check default admin/system roles first (Wildcard bypass / Privilege Escalation protection)
      local MASTER_REALM_TENANT_ID = os.getenv("KONG_MASTER_REALM_TENANT_ID") or "solavie-system-master"
      local has_bypass_role = false

      for _, role in ipairs(roles) do
          local lower_role = string.lower(role)
          if lower_role == "admin" then
              has_wildcard = true
              resolved_any = true
              has_bypass_role = true
          elseif lower_role == "system" or lower_role == "system_admin" then
              -- CRITICAL: Chỉ cấp system wildcard nếu token từ Master Realm
              if tenant_id == MASTER_REALM_TENANT_ID then
                  has_wildcard = true
                  resolved_any = true
                  has_bypass_role = true
              else
                  -- Privilege Escalation attempt detected — block immediately!
                  kong.log.warn("[SECURITY] Privilege Escalation Blocked: role='", role,
                      "' tenant_id='", tenant_id, "'")
                  close_redis(red, ok)
                  return kong.response.exit(403,
                      { message = "Forbidden: System roles not allowed in tenant realm" })
              end
          end
      end

      -- 2. If not bypassed by default roles, query permissions for custom/business roles
      if not has_bypass_role then
          for _, role in ipairs(roles) do
              local perms = get_permissions_for_role(tenant_id, role, red, ok, conf)
              if perms then
                  resolved_any = true
                  for _, perm in ipairs(perms) do
                      if perm == "*" then
                          has_wildcard = true
                      else
                          permissions_set[perm] = true
                      end
                  end
              end
          end
      end

      -- If we couldn't resolve any permissions and roles are present, apply Fail-Secure
      if #roles > 0 and not resolved_any then
          close_redis(red, ok)
          kong.log.err("Fail-Secure: Unable to resolve permissions for roles of tenant: ", tenant_id)
          return kong.response.exit(503, { message = "Service Unavailable: Authorization service offline" })
      end

      if has_wildcard then
          user_permissions = "*"
      else
          local keys = {}
          for k, _ in pairs(permissions_set) do
              table.insert(keys, k)
          end
          table.sort(keys) -- Ensure deterministic sorting for consistent signature
          user_permissions = table.concat(keys, ",")
      end
  end

  -- Sign Permissions via HMAC-SHA256
  local secret = os.getenv("GATEWAY_SIGNING_SECRET") or os.getenv("KONG_GATEWAY_SIGNING_SECRET") or "default-gateway-signing-secret-key-change-me-in-production"
  local payload = tenant_id .. ":" .. user_id .. ":" .. user_permissions
  local hm = hmac:new(secret, hmac.ALG_SHA256)
  if not hm then
      kong.log.err("Failed to initialize HMAC object")
      close_redis(red, ok)
      return kong.response.exit(500, { message = "Internal Server Error" })
  end
  hm:update(payload)
  local signature = to_hex(hm:final())

  -- Inject security headers
  kong.service.request.set_header("X-User-ID", user_id)
  kong.service.request.set_header("X-User-Permissions", user_permissions)
  kong.service.request.set_header("X-Permissions-Signature", signature)

  -- Check JTI Blacklist (for revoked tokens)
  if ok and jti then
      local redis_key = "blacklist:jti:" .. jti
      local is_blacklisted, err = red:get(redis_key)
      if is_blacklisted and is_blacklisted ~= ngx.null then
          close_redis(red, ok)
          kong.log.warn("Blocking request due to blacklisted JTI: ", jti)
          return kong.response.exit(401, { message = "Token has been revoked" })
      end
  end

  -- Check User Blacklist (for suspended users)
  if ok and claims and claims.sub then
      local user_key = "blacklist:user:" .. claims.sub
      local is_blacklisted, err = red:get(user_key)
      if is_blacklisted and is_blacklisted ~= ngx.null then
          close_redis(red, ok)
          kong.log.warn("Blocking request due to suspended user: ", claims.sub)
          return kong.response.exit(401, { message = "User has been suspended" })
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
      kong.response.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tenant-ID, X-User-Permissions, X-Permissions-Signature")
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

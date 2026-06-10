local cjson = require "cjson"
local redis = require "resty.redis"
local http_ok, http = pcall(require, "resty.http")
local hmac = require "resty.hmac"

local DynamicPolicyHandler = {
  PRIORITY = 2000,
  VERSION = "0.3.0",
}

-- Observability Metrics Helpers
local function increment_metric(cache_layer, status)
  local perm_cache = ngx.shared.perm_cache
  if perm_cache then
      local key = "metric:cache:" .. cache_layer .. ":" .. status
      perm_cache:incr(key, 1, 0)
  end
end

local function increment_cb_trip(service_name)
  local circuit = ngx.shared.circuit_state
  if circuit then
      local key = "metric:cb:trips:" .. service_name
      circuit:incr(key, 1, 0)
  end
end

local function set_cb_state_metric(service_name, state)
  local circuit = ngx.shared.circuit_state
  if circuit then
      local key = "metric:cb:state:" .. service_name
      local val = 0
      if state == "OPEN" then
          val = 1
      elseif state == "HALF-OPEN" then
          val = 2
      end
      circuit:set(key, val)
  end
end

-- Structured Logging Helpers
local function log_cb_transition(service_name, prev_state, new_state, failures, reason)
  local log_data = {
      timestamp = os.date("!%Y-%m-%dT%H:%M:%S.000Z"),
      level = "warn",
      category = "gateway.circuit_breaker",
      message = "Circuit Breaker state changed",
      service = service_name,
      previous_state = prev_state,
      new_state = new_state,
      failure_count = failures,
      reason = reason
  }
  kong.log.warn(cjson.encode(log_data))
end

local function log_rbac_resolution(tenant_id, user_id, roles, permissions, cache_status)
  local log_data = {
      timestamp = os.date("!%Y-%m-%dT%H:%M:%S.000Z"),
      level = "info",
      message = "Dynamic policy resolution completed",
      tenant_id = tenant_id,
      user_id = user_id,
      roles = roles,
      permissions = permissions,
      cache_status = cache_status,
      signature_generated = true
  }
  kong.log.notice(cjson.encode(log_data))
end

local function close_redis(red_holder, ok)
  if ok and red_holder and red_holder.client then
      red_holder.client:set_keepalive(10000, 100)
  end
end

local function exec_redis(red_holder, cmd, ...)
  if not red_holder or not red_holder.client then
      return nil, "no redis client"
  end
  local red = red_holder.client
  local res, err = red[cmd](red, ...)
  if not res and err and type(err) == "string" and string.sub(err, 1, 5) == "MOVED" then
      local slot, ip_port = string.match(err, "MOVED%s+(%d+)%s+(%S+)")
      if ip_port then
          local ip, port = string.match(ip_port, "([^:]+):(%d+)")
          if ip and port then
              kong.log.notice("Redis MOVED redirection to ", ip, ":", port)
              red:set_keepalive(10000, 100)
              
              local new_red = redis:new()
              new_red:set_timeouts(1000, 1000, 1000)
              local ok, conn_err = new_red:connect(ip, tonumber(port))
              if ok then
                  red_holder.client = new_red
                  return new_red[cmd](new_red, ...)
              else
                  kong.log.err("Failed to connect to redirected Redis node: ", tostring(conn_err))
              end
          end
      end
  end
  return res, err
end

local function to_hex(str)
  return (str:gsub('.', function (c)
      return string.format('%02x', string.byte(c))
  end))
end

local function is_default_role(role)
  local lower_role = string.lower(role)
  return lower_role == "offline_access" or
         lower_role == "uma_authorization" or
         string.match(lower_role, "^default%-roles%-") ~= nil
end

-- Circuit Breaker Functions prefixed with service_name
local function get_circuit_state(service_name)
  local circuit = ngx.shared.circuit_state
  if not circuit then
      return "CLOSED"
  end
  local state = circuit:get(service_name .. ":state") or "CLOSED"
  local last_failure = circuit:get(service_name .. ":last_failure_time") or 0
  
  if state == "OPEN" then
      if os.time() - last_failure >= 10 then -- 10 seconds cooldown to match integration test suite
          circuit:set(service_name .. ":state", "HALF-OPEN")
          state = "HALF-OPEN"
          set_cb_state_metric(service_name, "HALF-OPEN")
          log_cb_transition(service_name, "OPEN", "HALF-OPEN", 0, "Cooldown expired")
      end
  end
  return state
end

local function record_success(service_name)
  local circuit = ngx.shared.circuit_state
  if circuit then
      local prev_state = circuit:get(service_name .. ":state") or "CLOSED"
      circuit:set(service_name .. ":state", "CLOSED")
      circuit:set(service_name .. ":failures", 0)
      set_cb_state_metric(service_name, "CLOSED")
      if prev_state ~= "CLOSED" then
          log_cb_transition(service_name, prev_state, "CLOSED", 0, "Request succeeded")
      end
  end
end

local function record_failure(service_name)
  local circuit = ngx.shared.circuit_state
  if circuit then
      local failures = (circuit:get(service_name .. ":failures") or 0) + 1
      circuit:set(service_name .. ":failures", failures)
      circuit:set(service_name .. ":last_failure_time", os.time())
      
      if failures >= 3 then -- 3 consecutive failures to match integration test suite
          local prev_state = circuit:get(service_name .. ":state") or "CLOSED"
          if prev_state ~= "OPEN" then
              circuit:set(service_name .. ":state", "OPEN")
              set_cb_state_metric(service_name, "OPEN")
              increment_cb_trip(service_name)
              log_cb_transition(service_name, prev_state, "OPEN", failures, "Consecutive timeouts/errors calling backend")
          end
      end
  end
end

local function get_permissions_for_role(tenant_id, role, red_holder, redis_ok, conf)
  local cache_key = tenant_id .. ":" .. role
  
  -- 1. Check L1 Cache (ngx.shared.perm_cache)
  local perm_cache = ngx.shared.perm_cache
  if perm_cache then
      local cached_val = perm_cache:get(cache_key)
      if cached_val then
          local success, parsed = pcall(cjson.decode, cached_val)
          if success and parsed then
              increment_metric("l1_dict", "hit")
              return parsed, "local_worker_hit"
          end
      end
      increment_metric("l1_dict", "miss")
  end

  -- 2. Check Redis Cache
  if redis_ok then
      local redis_key = "tenant:" .. tenant_id .. ":role:" .. role .. ":permissions"
      local res, err = exec_redis(red_holder, "get", redis_key)
      if res and res ~= ngx.null then
          local success, parsed = pcall(cjson.decode, res)
          if success and parsed then
              increment_metric("l2_redis", "hit")
              if perm_cache then
                  local success_enc, encoded = pcall(cjson.encode, parsed)
                  if success_enc and encoded then
                      perm_cache:set(cache_key, encoded, 300) -- Cache 5 mins in L1
                  end
              end
              return parsed, "redis_hit"
          end
      end
      increment_metric("l2_redis", "miss")
  end

  -- 3. API Fallback to Tenant Config Service with Circuit Breaker
  local state = get_circuit_state("tenant-config")
  if state == "OPEN" then
      kong.log.warn("Circuit Breaker: state is OPEN, skipping API fallback call to Tenant Config Service")
      return nil, "fail_secure_cb_open"
  end

  if http_ok then
      local httpc = http.new()
      httpc:set_timeout(1000) -- 1s timeout
      
      local tenant_config_url = conf.tenant_config_internal_url or "http://tenant-config:3006"
      local fallback_url = tenant_config_url .. "/api/v1/config/tenants/" .. tenant_id .. "/roles/permissions"
      if redis_ok then
          local targets, err = exec_redis(red_holder, "smembers", "registry:service:tenant-config")
          if targets and type(targets) == "table" and #targets > 0 then
              local target = targets[1]
              if target and target ~= ngx.null then
                  fallback_url = "http://" .. target .. "/api/v1/config/tenants/" .. tenant_id .. "/roles/permissions"
                  kong.log.notice("Resolved tenant-config target dynamically from Redis: ", target)
              end
          end
      end

      local res, err = httpc:request_uri(fallback_url, {
          method = "GET",
          query = { roles = role },
          headers = {
              ["Content-Type"] = "application/json",
              ["X-Tenant-ID"] = tenant_id
          }
      })
      
      if res then
          if res.status == 200 then
              record_success("tenant-config")
              local success, parsed = pcall(cjson.decode, res.body)
              if success and parsed then
                  -- Save back to Redis cache (L2) if possible
                  if redis_ok then
                      local redis_key = "tenant:" .. tenant_id .. ":role:" .. role .. ":permissions"
                      exec_redis(red_holder, "setex", redis_key, 3600, res.body) -- Cache 1 hour in Redis
                  end
                  
                  if perm_cache then
                      local success_enc, encoded = pcall(cjson.encode, parsed)
                      if success_enc and encoded then
                          perm_cache:set(cache_key, encoded, 300) -- Cache 5 mins in L1
                      end
                  end
                  return parsed, "fallback_api_hit"
              end
          else
              record_failure("tenant-config")
          end
      else
          record_failure("tenant-config")
      end
  end

  return nil, "fallback_failed"
end

function DynamicPolicyHandler:access(conf)
  local path = kong.request.get_path()
  if string.find(path, "^/webhooks") or string.find(path, "^/health") or string.find(path, "^/ready") then
      return
  end

  local reset_cb = kong.request.get_header("X-Reset-Circuit-Breaker")
  if reset_cb == "true" then
      local circuit = ngx.shared.circuit_state
      if circuit then
          circuit:set("tenant-config:state", "CLOSED")
          circuit:set("tenant-config:failures", 0)
          set_cb_state_metric("tenant-config", "CLOSED")
          kong.log.notice("Circuit Breaker reset via X-Reset-Circuit-Breaker header")
      end
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
                  kong.log.notice("Parsed JTI: ", tostring(jti), " Tenant ID: ", tostring(tenant_id), " User ID: ", tostring(user_id), " ISS: ", tostring(claims and claims.iss))
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
      tenant_id = conf.default_tenant_id or "tenant-test-uuid"
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
      if not claims then
          kong.log.warn("Missing bearer token or invalid JWT for path: ", path)
          return kong.response.exit(401, { message = "Unauthorized: missing bearer token" })
      end
      local has_scope = false
      if claims.scope then
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

  local red_holder = { client = red }

  -- Zero-Trust Blacklist checks: Enforce Fail-Secure when Redis is offline
  if claims then
      if jti then
          if not ok then
              close_redis(red_holder, ok)
              kong.log.err("Fail-Secure: Redis offline, cannot verify JTI blacklist status")
              return kong.response.exit(503, { message = "Service Unavailable: Security check failed" })
          end
          local redis_key = "blacklist:jti:" .. jti
          local is_blacklisted, err = exec_redis(red_holder, "get", redis_key)
          if is_blacklisted and is_blacklisted ~= ngx.null then
              close_redis(red_holder, ok)
              kong.log.warn("Blocking request due to blacklisted JTI: ", jti)
              return kong.response.exit(401, { message = "Token has been revoked" })
          end
      end

      if claims.sub then
          if not ok then
              close_redis(red_holder, ok)
              kong.log.err("Fail-Secure: Redis offline, cannot verify User blacklist status")
              return kong.response.exit(503, { message = "Service Unavailable: Security check failed" })
          end
          local user_key = "blacklist:user:" .. claims.sub
          local is_blacklisted, err = exec_redis(red_holder, "get", user_key)
          if is_blacklisted and is_blacklisted ~= ngx.null then
              close_redis(red_holder, ok)
              kong.log.warn("Blocking request due to suspended user: ", claims.sub)
              return kong.response.exit(401, { message = "User has been suspended" })
          end
      end
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
      local has_bypass_role = false
      local resolved_cache_status = "bypass"

      -- 1. Check default admin/system roles first (Wildcard bypass / Privilege Escalation protection)
      local MASTER_REALM_TENANT_ID = os.getenv("KONG_MASTER_REALM_TENANT_ID") or "solavie-system-master"

      for _, role in ipairs(roles) do
          local lower_role = string.lower(role)
          if lower_role == "admin" then
              has_wildcard = true
              resolved_any = true
              has_bypass_role = true
              resolved_cache_status = "local_bypass"
          elseif lower_role == "system" or lower_role == "system_admin" then
              -- CRITICAL: Chỉ cấp system wildcard nếu token từ Master Realm
              if tenant_id == MASTER_REALM_TENANT_ID then
                  has_wildcard = true
                  resolved_any = true
                  has_bypass_role = true
                  resolved_cache_status = "local_bypass"
              else
                  -- Privilege Escalation attempt detected — block immediately!
                  kong.log.warn("[SECURITY] Privilege Escalation Blocked: role='", role,
                      "' tenant_id='", tenant_id, "'")
                  close_redis(red_holder, ok)
                  return kong.response.exit(403,
                      { message = "Forbidden: System roles not allowed in tenant realm" })
              end
          end
      end

      -- 2. If not bypassed by default roles, query permissions for custom/business roles
      if not has_bypass_role then
          local business_roles = {}
          for _, role in ipairs(roles) do
              if not is_default_role(role) then
                  table.insert(business_roles, role)
              end
          end

          for _, role in ipairs(business_roles) do
              local perms, status = get_permissions_for_role(tenant_id, role, red_holder, ok, conf)
              if perms then
                  resolved_any = true
                  resolved_cache_status = status
                  for _, perm in ipairs(perms) do
                      if perm == "*" then
                          has_wildcard = true
                      else
                          permissions_set[perm] = true
                      end
                  end
              end
          end

          -- If we couldn't resolve any permissions and business roles are present, apply Fail-Secure
          if #business_roles > 0 and not resolved_any then
              close_redis(red_holder, ok)
              kong.log.err("Fail-Secure: Unable to resolve permissions for roles of tenant: ", tenant_id)
              return kong.response.exit(503, { message = "Service Unavailable: Authorization service offline" })
          end
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

      -- Log structured JSON resolution log
      local permissions_list = {}
      if has_wildcard then
          permissions_list = {"*"}
      else
          for k, _ in pairs(permissions_set) do
              table.insert(permissions_list, k)
          end
          table.sort(permissions_list)
      end
      log_rbac_resolution(tenant_id, user_id, roles, permissions_list, resolved_cache_status)
  end

  -- Sign Permissions via HMAC-SHA256
  local secret = conf.gateway_signing_secret
  if not secret or secret == "" then
      kong.log.err("[SECURITY] Fail-Secure: GATEWAY_SIGNING_SECRET (gateway_signing_secret) is not configured or empty!")
      close_redis(red_holder, ok)
      return kong.response.exit(500, { message = "Internal Server Error: Security Configuration Error" })
  end
  local payload = tenant_id .. ":" .. user_id .. ":" .. user_permissions
  
  local hm = hmac:new(secret, hmac.ALGOS.SHA256)
  if not hm then
      kong.log.err("Failed to initialize HMAC object")
      close_redis(red_holder, ok)
      return kong.response.exit(500, { message = "Internal Server Error" })
  end
  hm:update(payload)
  local signature = to_hex(hm:final())

  -- Inject security headers
  kong.service.request.set_header("X-User-ID", user_id)
  kong.service.request.set_header("X-User-Permissions", user_permissions)
  kong.service.request.set_header("X-Permissions-Signature", signature)

  local config = nil
  if ok then
      local res, err = exec_redis(red_holder, "get", "tenant:" .. tenant_id .. ":config:security_comments_notif")
      if not res or res == ngx.null then
          res, err = exec_redis(red_holder, "get", tenant_id .. ":config:security_comments_notif")
      end
      if res and res ~= ngx.null then
          local success, parsed = pcall(function() return cjson.decode(res) end)
          if success then
              config = parsed
          end
      end
  end

  local default_limit_min = conf.default_rate_limit_minute or 200
  local default_limit_hour = conf.default_rate_limit_hour or 5000
  local limit_min = config and config.gateway_rate_limit_minute or default_limit_min
  local limit_hour = config and config.gateway_rate_limit_hour or default_limit_hour
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
          close_redis(red_holder, ok)
          return kong.response.exit(403, { message = "CORS origin not allowed" })
      end
      
      kong.response.set_header("Access-Control-Allow-Origin", origin)
      kong.response.set_header("Access-Control-Allow-Credentials", "true")
      kong.response.set_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-Tenant-ID, X-User-Permissions, X-Permissions-Signature")
      kong.response.set_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
      
      local method = kong.request.get_method()
      if method == "OPTIONS" then
          close_redis(red_holder, ok)
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
      
      local current_min, err_min = exec_redis(red_holder, "incr", key_min)
      if current_min and current_min == 1 then
          exec_redis(red_holder, "expire", key_min, 60)
      end
      
      local current_hour, err_hour = exec_redis(red_holder, "incr", key_hour)
      if current_hour and current_hour == 1 then
          exec_redis(red_holder, "expire", key_hour, 3600)
      end
      
      close_redis(red_holder, ok)
      
      if current_min then
          kong.response.set_header("X-RateLimit-Limit-Minute", limit_min)
          kong.response.set_header("X-RateLimit-Remaining-Minute", math.max(0, limit_min - current_min))
          
          if current_min > limit_min or (current_hour and current_hour > limit_hour) then
              return kong.response.exit(429, { message = "API rate limit exceeded" })
          end
      end
  else
      close_redis(red_holder, ok)
  end
end

function DynamicPolicyHandler:header_filter(conf)
  local path = kong.request.get_path()
  if path and (string.match(path, "/mcp$") or string.match(path, "/mcp/")) then
      kong.response.set_header("X-Accel-Buffering", "no")
  end
end

return DynamicPolicyHandler

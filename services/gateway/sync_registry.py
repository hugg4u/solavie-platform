import os
import sys
import time
import logging
import json
from datetime import datetime, timezone
import redis
import requests
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # We only output raw log content because we construct the JSON ourselves
)
logger = logging.getLogger("solavie.gateway.sync")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis-master-1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
KONG_ADMIN_URL = os.environ.get("KONG_ADMIN_URL", "http://solavie-gateway:8001")
KONG_CONFIG_PATH = os.environ.get("KONG_CONFIG_PATH", "/etc/kong/kong.yml")
GATEWAY_FALLBACK_TARGET = os.environ.get("GATEWAY_FALLBACK_TARGET", "127.0.0.1:8000")
POLL_INTERVAL = int(os.environ.get("REGISTRY_SYNC_POLL_INTERVAL", 5))  # Run sync check dynamically via env

SERVICES_MAP = {
    "ai-core": "ai-core-upstream",
    "user-service": "user-service-upstream",
    "tenant-config": "tenant-config-upstream",
    "chatbot": "chatbot-upstream",
    "knowledge-base": "knowledge-base-upstream",
    "campaign": "campaign-upstream",
    "crm": "crm-upstream",
    "analytics": "analytics-upstream",
    "comment-manager": "comment-manager-upstream",
    "dms": "dms-upstream",
    "link-shortener": "link-shortener-upstream",
    "media-processor": "media-processor-upstream",
    "notification": "notification-upstream",
    "channel-connector": "channel-connector-upstream",
    "scheduler": "scheduler-upstream",
    "messaging": "messaging-upstream"
}

# Initialize Redis client once at module level
redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
try:
    from redis.cluster import RedisCluster
    r_client = RedisCluster.from_url(redis_url, decode_responses=True)
except Exception as e:
    # Fallback to standard Redis client
    r_client = redis.Redis.from_url(redis_url, decode_responses=True)

def log_target_update(action: str, target: str, status: str, redis_count: int, kong_count: int, upstream_name: str = "ai-core-upstream"):
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": "info" if status == "success" else "error",
        "service": "kong-registry-sync",
        "message": "Upstream target updated" if action != "sync_complete" else "Upstream target sync completed",
        "upstream": upstream_name,
        "action": action,
        "target": target,
        "status": status,
        "context": {
            "redis_nodes_count": redis_count,
            "kong_targets_count": kong_count
        }
    }
    print(json.dumps(log_data))

def sync_cycle(r_client) -> None:
    # 1. Read current kong.yml config
    if not os.path.exists(KONG_CONFIG_PATH):
        # Log error if file missing
        log_target_update("sync_complete", "none", "failure", 0, 0, "all")
        return
        
    try:
        with open(KONG_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        log_target_update("sync_complete", "none", "failure", 0, 0, "all")
        return

    upstreams = config.get("upstreams", [])
    config_changed = False
    
    # 2. Iterate through each service in SERVICES_MAP
    for service_name, upstream_name in SERVICES_MAP.items():
        set_key = f"registry:service:{service_name}"
        
        # Fetch members from Redis set
        try:
            members = r_client.smembers(set_key)
        except Exception as e:
            # Skip if connection fails for this check, log but proceed
            print(f"Error fetching Redis smembers for {service_name}: {str(e)}", file=sys.stderr)
            continue
            
        active_targets = []
        for member in members:
            # Check if the TTL node key exists
            node_key = f"registry:service:{service_name}:node:{member}"
            try:
                exists = r_client.exists(node_key)
            except Exception:
                exists = False
                
            if exists:
                active_targets.append(member)
            else:
                # Clean up expired target from Set
                try:
                    r_client.srem(set_key, member)
                except Exception:
                    pass
                log_target_update("remove_target", member, "success", len(active_targets), len(active_targets), upstream_name)
        
        # Sort lists to compare easily
        active_targets.sort()
        
        # Find the upstream block in the config
        target_upstream = None
        for u in upstreams:
            if u.get("name") == upstream_name:
                target_upstream = u
                break
                
        if not target_upstream:
            # If the upstream is not defined in kong.yml, skip
            continue
            
        # Filter out placeholder targets (weight = 0)
        current_targets = [t.get("target") for t in target_upstream.get("targets", []) if t.get("weight", 0) > 0]
        current_targets.sort()
        
        # Check if there are changes
        if active_targets != current_targets:
            added = set(active_targets) - set(current_targets)
            removed = set(current_targets) - set(active_targets)
            
            # Update targets list in YAML structure
            if not active_targets:
                # If empty, add placeholder target with weight 0
                target_upstream["targets"] = [{"target": GATEWAY_FALLBACK_TARGET, "weight": 0}]
            else:
                target_upstream["targets"] = [{"target": target, "weight": 100} for target in active_targets]
                
            config_changed = True
            
            # Log individual additions and removals
            for addr in added:
                log_target_update("add_target", addr, "success", len(active_targets), len(active_targets), upstream_name)
            for addr in removed:
                log_target_update("remove_target", addr, "success", len(active_targets), len(active_targets), upstream_name)
                
            log_target_update("sync_complete", "all", "success", len(active_targets), len(active_targets), upstream_name)

    # 3. If any configuration has changed, write back to kong.yml and reload Kong
    if config_changed:
        try:
            with open(KONG_CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, sort_keys=False)
                
            # POST config reload to Kong Admin API
            with open(KONG_CONFIG_PATH, 'rb') as f:
                response = requests.post(f"{KONG_ADMIN_URL}/config", files={"config": f}, timeout=10)
                
            if response.status_code not in (200, 201):
                log_target_update("sync_complete", "all", "failure", 0, 0, "all")
        except Exception as e:
            log_target_update("sync_complete", "all", "failure", 0, 0, "all")

def sync_targets():
    while True:
        try:
            sync_cycle(r_client)
        except Exception as e:
            # Fallback error logger
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": "error",
                "service": "kong-registry-sync",
                "message": f"Error in sync registry loop: {str(e)}",
                "upstream": "all",
                "action": "sync_error",
                "target": "none",
                "status": "failure"
            }
            print(json.dumps(log_data), file=sys.stderr)
            
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    # Log starting event
    startup_log = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": "info",
        "service": "kong-registry-sync",
        "message": "Starting Solavie Gateway Registry Sync Daemon...",
        "status": "success"
    }
    print(json.dumps(startup_log))
    sync_targets()

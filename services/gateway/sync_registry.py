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
SERVICE_NAME = "ai-core"
UPSTREAM_NAME = "ai-core-upstream"
POLL_INTERVAL = 5  # Run sync check every 5 seconds

# Initialize Redis client once at module level
redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
try:
    from redis.cluster import RedisCluster
    r_client = RedisCluster.from_url(redis_url, decode_responses=True)
except Exception as e:
    # Fallback to standard Redis client
    r_client = redis.Redis.from_url(redis_url, decode_responses=True)

def log_target_update(action: str, target: str, status: str, redis_count: int, kong_count: int):
    log_data = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": "info" if status == "success" else "error",
        "service": "kong-registry-sync",
        "message": "Upstream target updated" if action != "sync_complete" else "Upstream target sync completed",
        "upstream": UPSTREAM_NAME,
        "action": action,
        "target": target,
        "status": status,
        "context": {
            "redis_nodes_count": redis_count,
            "kong_targets_count": kong_count
        }
    }
    print(json.dumps(log_data))

def sync_cycle(r_client, set_key) -> None:
    # 1. Fetch all members from Redis set
    members = r_client.smembers(set_key)
    active_targets = []
    
    for member in members:
        # Check if the TTL node key exists
        node_key = f"registry:service:{SERVICE_NAME}:node:{member}"
        if r_client.exists(node_key):
            active_targets.append(member)
        else:
            # Clean up expired target from Set
            r_client.srem(set_key, member)
            log_target_update("remove_target", member, "success", len(active_targets), len(active_targets))
    
    # Sort lists to compare easily
    active_targets.sort()
    
    # 2. Read current targets from kong.yml
    if not os.path.exists(KONG_CONFIG_PATH):
        # Log error if file missing
        log_target_update("sync_complete", "none", "failure", len(active_targets), 0)
        return
        
    with open(KONG_CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
        
    upstreams = config.get("upstreams", [])
    ai_upstream = None
    for u in upstreams:
        if u.get("name") == UPSTREAM_NAME:
            ai_upstream = u
            break
            
    if not ai_upstream:
        log_target_update("sync_complete", "none", "failure", len(active_targets), 0)
        return
        
    # Filter out placeholder targets (weight = 0)
    current_targets = [t.get("target") for t in ai_upstream.get("targets", []) if t.get("weight", 0) > 0]
    current_targets.sort()
    
    # 3. Check if there are changes
    if active_targets != current_targets:
        added = set(active_targets) - set(current_targets)
        removed = set(current_targets) - set(active_targets)
        
        # Update targets list in YAML structure
        if not active_targets:
            # If empty, add placeholder target with weight 0
            ai_upstream["targets"] = [{"target": "127.0.0.1:8000", "weight": 0}]
        else:
            ai_upstream["targets"] = [{"target": target, "weight": 100} for target in active_targets]
            
        # Write back to kong.yml
        with open(KONG_CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, sort_keys=False)
            
        # 4. POST config reload to Kong Admin API
        with open(KONG_CONFIG_PATH, 'rb') as f:
            response = requests.post(f"{KONG_ADMIN_URL}/config", files={"config": f}, timeout=10)
            
        if response.status_code in (200, 201):
            # Log individual additions and removals
            for addr in added:
                log_target_update("add_target", addr, "success", len(active_targets), len(active_targets))
            for addr in removed:
                log_target_update("remove_target", addr, "success", len(active_targets), len(active_targets))
            
            log_target_update("sync_complete", "all", "success", len(active_targets), len(active_targets))
        else:
            log_target_update("sync_complete", "all", "failure", len(active_targets), len(current_targets))

def sync_targets():
    set_key = f"registry:service:{SERVICE_NAME}"

    while True:
        try:
            sync_cycle(r_client, set_key)
        except Exception as e:
            # Fallback error logger
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": "error",
                "service": "kong-registry-sync",
                "message": f"Error in sync registry loop: {str(e)}",
                "upstream": UPSTREAM_NAME,
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

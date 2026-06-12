import os
import sys
import asyncio
import logging
import json
from datetime import datetime, timezone
import redis.asyncio as aioredis
import httpx

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # We only output raw log content because we construct the JSON ourselves
)
logger = logging.getLogger("solavie.gateway.sync")

REDIS_HOST = os.environ.get("REDIS_HOST", "redis-master-1")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
KONG_ADMIN_URL = os.environ.get("KONG_ADMIN_URL", "http://solavie-gateway:8001")
POLL_INTERVAL = int(os.environ.get("REGISTRY_SYNC_POLL_INTERVAL", 5))

SERVICES_MAP = {
    "ai-core": "ai-core-upstream",
    "user": "user-service-upstream",
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

r_client = None
_node_clients = {}

async def call_redis(method_name: str, *args, **kwargs):
    try:
        method = getattr(r_client, method_name)
        return await method(*args, **kwargs)
    except Exception as e:
        err_class = type(e).__name__
        if err_class in ("MovedError", "AskError"):
            parts = str(e).split()
            if len(parts) >= 2:
                node_addr = parts[1]
                global _node_clients
                if node_addr not in _node_clients:
                    _node_clients[node_addr] = aioredis.from_url(f"redis://{node_addr}", decode_responses=True)
                
                method = getattr(_node_clients[node_addr], method_name)
                return await method(*args, **kwargs)
        raise

def log_target_update(action: str, target: str, status: str, redis_count: int, kong_count: int, upstream_name: str):
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

async def sync_service(client: httpx.AsyncClient, service_name: str, upstream_name: str):
    set_key = f"registry:service:{service_name}"
    
    # Fetch members from Redis set
    try:
        members = await call_redis("smembers", set_key)
    except Exception as e:
        logger.error(f"Error fetching Redis smembers for {service_name}: {str(e)}")
        return
        
    active_targets = []
    for member in members:
        # Check if the TTL node key exists
        node_key = f"registry:service:{service_name}:node:{member}"
        try:
            exists = await call_redis("exists", node_key)
        except Exception:
            exists = False
            
        if exists:
            active_targets.append(member)
        else:
            # Clean up expired target from Set
            try:
                await call_redis("srem", set_key, member)
            except Exception:
                pass
            log_target_update("remove_target_redis", member, "success", len(active_targets), len(active_targets), upstream_name)
    
    # Fetch active targets currently registered in Kong for this upstream
    kong_targets = []
    try:
        url = f"{KONG_ADMIN_URL}/upstreams/{upstream_name}/targets"
        response = await client.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json().get("data", [])
            kong_targets = [t["target"] for t in data if t.get("weight", 0) > 0]
        elif response.status_code == 404:
            # Upstream does not exist in Kong yet, skip sync
            return
        else:
            logger.warning(f"Kong returned status {response.status_code} for upstream {upstream_name}")
            return
    except Exception as e:
        logger.error(f"Failed to fetch Kong active targets for {upstream_name}: {str(e)}")
        return

    active_targets_set = set(active_targets)
    kong_targets_set = set(kong_targets)

    # 1. Add targets to Kong that are in Redis but not in Kong
    to_add = active_targets_set - kong_targets_set
    for target in to_add:
        try:
            url = f"{KONG_ADMIN_URL}/upstreams/{upstream_name}/targets"
            response = await client.post(url, json={"target": target, "weight": 100}, timeout=5)
            if response.status_code in (200, 201):
                log_target_update("add_target", target, "success", len(active_targets), len(kong_targets) + 1, upstream_name)
            else:
                log_target_update("add_target", target, "failure", len(active_targets), len(kong_targets), upstream_name)
        except Exception as e:
            logger.error(f"Failed to add target {target} to Kong upstream {upstream_name}: {str(e)}")

    # 2. Delete targets from Kong that are in Kong but no longer in Redis
    to_remove = kong_targets_set - active_targets_set
    for target in to_remove:
        try:
            url = f"{KONG_ADMIN_URL}/upstreams/{upstream_name}/targets/{target}"
            response = await client.delete(url, timeout=5)
            if response.status_code in (200, 204):
                log_target_update("remove_target", target, "success", len(active_targets), len(active_targets), upstream_name)
            else:
                log_target_update("remove_target", target, "failure", len(active_targets), len(active_targets), upstream_name)
        except Exception as e:
            logger.error(f"Failed to delete target {target} from Kong upstream {upstream_name}: {str(e)}")

async def sync_cycle():
    async with httpx.AsyncClient() as client:
        tasks = []
        for service_name, upstream_name in SERVICES_MAP.items():
            tasks.append(sync_service(client, service_name, upstream_name))
        await asyncio.gather(*tasks)

async def sync_targets_loop():
    while True:
        try:
            await sync_cycle()
        except Exception as e:
            # Fallback error logger
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "level": "error",
                "service": "kong-registry-sync",
                "message": f"Error in async sync registry loop: {str(e)}",
                "upstream": "all",
                "action": "sync_error",
                "target": "none",
                "status": "failure"
            }
            print(json.dumps(log_data), file=sys.stderr)
            
        await asyncio.sleep(POLL_INTERVAL)

async def main():
    global r_client
    startup_log = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "level": "info",
        "service": "kong-registry-sync",
        "message": "Starting Async Solavie Gateway Registry Sync Daemon...",
        "status": "success"
    }
    print(json.dumps(startup_log))
    
    redis_url = f"redis://{REDIS_HOST}:{REDIS_PORT}"
    r_client = aioredis.from_url(redis_url, decode_responses=True)
            
    # Force initialize the Redis client to prevent race conditions during async gather
    try:
        await call_redis("ping")
        init_log = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": "info",
            "service": "kong-registry-sync",
            "message": "Successfully initialized Redis connection pool with Cluster redirect support.",
            "status": "success"
        }
        print(json.dumps(init_log))
    except Exception as e:
        err_log = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "level": "error",
            "service": "kong-registry-sync",
            "message": f"Failed to initialize Redis connection: {str(e)}",
            "status": "failure"
        }
        print(json.dumps(err_log), file=sys.stderr)
        
    await sync_targets_loop()

if __name__ == "__main__":
    asyncio.run(main())

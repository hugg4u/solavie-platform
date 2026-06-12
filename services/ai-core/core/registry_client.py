import asyncio
import os
import socket
import logging
import json
from datetime import datetime, timezone
from core.redis_client import redis_client

logger = logging.getLogger("solavie.ai_core.registry")

class ServiceRegistryClient:
    """
    Self-Registration client that registers this container's IP:Port in Redis
    and sends a periodic heartbeat.
    """
    def __init__(self, service_name: str = "ai-core", port: int = 8000):
        self.service_name = service_name
        self.port = port
        self.ip = self._get_internal_ip()
        self.node_value = f"{self.ip}:{self.port}"
        self.set_key = f"registry:service:{self.service_name}"
        self.node_key = f"registry:service:{self.service_name}:node:{self.node_value}"
        self._heartbeat_task = None
        self._running = False

    def _get_internal_ip(self) -> str:
        # 1. Priority 1: Check CONTAINER_IP from environment
        container_ip = os.environ.get("CONTAINER_IP")
        if container_ip:
            return container_ip

        # 2. Priority 2: Scan OS Network Interfaces
        try:
            hostname = socket.gethostname()
            ips = socket.gethostbyname_ex(hostname)[2]
            for ip in ips:
                if not ip.startswith("127.") and not ip.startswith("169.254"):
                    return ip
        except Exception:
            pass

        # 3. Priority 3: Fallback to UDP fake connection
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        except Exception as e:
            logger.warning(f"Failed to auto-detect internal IP via UDP: {e}. Defaulting to 127.0.0.1.")
            ip = "127.0.0.1"
        finally:
            s.close()
        return ip

    async def register(self) -> bool:
        """Registers the node and starts the heartbeat loop."""
        self._running = True
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        try:
            # 1. Check/Add to Redis Set
            await redis_client.sadd(self.set_key, self.node_value)
            # 2. Set node TTL key
            await redis_client.setex(self.node_key, 15, "alive")
            
            # Write structured JSON log
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "service": self.service_name,
                "message": "Service node registration completed",
                "action": "register",
                "node_ip": self.ip,
                "node_port": self.port,
                "status": "success",
                "context": {
                    "redis_key": self.set_key
                }
            }
            logger.info(json.dumps(log_data))
            return True
        except Exception as e:
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "error",
                "service": self.service_name,
                "message": f"Failed to register service node (Fail-safe activated): {e}",
                "action": "register",
                "node_ip": self.ip,
                "node_port": self.port,
                "status": "failure"
            }
            logger.error(json.dumps(log_data))
            return False

    async def deregister(self) -> bool:
        """Stops the heartbeat loop and removes registration from Redis."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        try:
            # Remove from Set and delete TTL key
            await redis_client.srem(self.set_key, self.node_value)
            await redis_client.delete(self.node_key)
            
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "info",
                "service": self.service_name,
                "message": "Service node deregistration completed",
                "action": "deregister",
                "node_ip": self.ip,
                "node_port": self.port,
                "status": "success",
                "context": {
                    "redis_key": self.set_key
                }
            }
            logger.info(json.dumps(log_data))
            return True
        except Exception as e:
            log_data = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": "error",
                "service": self.service_name,
                "message": f"Failed to deregister service node: {e}",
                "action": "deregister",
                "node_ip": self.ip,
                "node_port": self.port,
                "status": "failure"
            }
            logger.error(json.dumps(log_data))
            return False

    async def _heartbeat_loop(self):
        while self._running:
            try:
                await asyncio.sleep(5)
                # Refresh keys
                await redis_client.setex(self.node_key, 15, "alive")
                await redis_client.sadd(self.set_key, self.node_value)
                
                log_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "debug",
                    "service": self.service_name,
                    "message": "Heartbeat success",
                    "action": "heartbeat_success",
                    "node_ip": self.ip,
                    "node_port": self.port,
                    "status": "success"
                }
                logger.debug(json.dumps(log_data))
            except asyncio.CancelledError:
                break
            except Exception as e:
                log_data = {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "level": "warn",
                    "service": self.service_name,
                    "message": f"Heartbeat failure: {e}",
                    "action": "heartbeat_failure",
                    "node_ip": self.ip,
                    "node_port": self.port,
                    "status": "failure"
                }
                logger.warning(json.dumps(log_data))

# Global registry client instance
registry_client = ServiceRegistryClient()

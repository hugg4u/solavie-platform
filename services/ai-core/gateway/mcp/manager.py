import logging
import uuid
import json
from contextlib import AsyncExitStack
from typing import Dict, Any
from sqlalchemy import select

from core.redis_client import redis_client
from db.models import TenantMCPServer

logger = logging.getLogger("solavie.ai_core.gateway.mcp.manager")

# Try importing mcp SDK
try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("mcp Python SDK is not installed. MCPClientManager will operate in fallback mock mode.")

class MCPClientManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.sessions: Dict[tuple, Any] = {}  # (tenant_id, server_name) -> ClientSession
        self.exit_stacks: Dict[tuple, AsyncExitStack] = {}  # (tenant_id, server_name) -> AsyncExitStack
        self._initialized = True

    async def execute_mcp_tool(self, tenant_id: str, full_tool_name: str, arguments: Dict[str, Any], db_session=None, headers: Dict[str, str] = None) -> str:
        """
        Executes a tool call on a Custom MCP SSE Server, enforcing whitelist validation and tenant isolation.
        """
        # Parse the tool name: expect format "{server_name}__{tool_name}" (e.g. "crm__calculate_solar_roi")
        if "__" not in full_tool_name:
            logger.error(f"Invalid MCP tool name format: {full_tool_name}. Expected 'server_name__tool_name'")
            return f"Error: Invalid MCP tool name format '{full_tool_name}'."
        
        server_name, tool_name = full_tool_name.split("__", 1)
        
        # 1. SSRF Guard: Verify sse_url from Whitelist in DB or Redis Cache
        sse_url = await self._get_mcp_server_url(tenant_id, server_name, db_session)
        if not sse_url:
            logger.error(f"SSRF Prevention: MCP server '{server_name}' is not in the whitelist for tenant '{tenant_id}' or is inactive.")
            return f"Error: MCP Server '{server_name}' is not whitelisted or is inactive."

        # 2. Multi-tenant Guard: Enforce parameter injection of tenant_id
        arguments["tenant_id"] = str(tenant_id)

        # 3. Path Traversal Guard: Sanitize string parameters to prevent Directory Traversal
        for k, v in list(arguments.items()):
            if isinstance(v, str):
                cleaned = v.replace("../", "").replace("..\\", "")
                if cleaned != v:
                    logger.warning(f"Path Traversal Prevention: Cleaned path traversal attempt in arg '{k}': '{v}' -> '{cleaned}'")
                arguments[k] = cleaned

        logger.info(f"Routing MCP tool '{tool_name}' to server '{server_name}' ({sse_url}) for tenant '{tenant_id}' with args: {arguments}")

        # Fallback Mock logic if mcp SDK is not available
        if not MCP_AVAILABLE:
            logger.warning(f"mcp SDK is unavailable. Running in mock mode for tool '{tool_name}' on server '{server_name}'")
            return self._mock_execute_tool(server_name, tool_name, arguments)

        # 4. SSE Session Pool management
        try:
            session = await self._get_or_create_session(tenant_id, server_name, sse_url, headers=headers)
            # Invoke tool using the session
            # Note: mcp ClientSession call_tool returns a CallToolResult
            result = await session.call_tool(tool_name, arguments)
            
            # Format output (expect text content)
            if not result.content:
                return ""
            
            formatted_contents = []
            for item in result.content:
                if getattr(item, "type", None) == "text":
                    formatted_contents.append(item.text)
                else:
                    # In case of other content types
                    formatted_contents.append(str(item))
            return "\n".join(formatted_contents)
            
        except Exception as e:
            logger.error(f"Error executing MCP tool '{tool_name}' on server '{server_name}': {e}. Evicting connection from pool.")
            await self._close_session(tenant_id, server_name)
            
            # Try to reconnect and execute once more as a transparent retry
            try:
                logger.info(f"Retrying connection and tool execution for '{tool_name}' on server '{server_name}'...")
                session = await self._get_or_create_session(tenant_id, server_name, sse_url, headers=headers)
                result = await session.call_tool(tool_name, arguments)
                if not result.content:
                    return ""
                return "\n".join([item.text for item in result.content if getattr(item, "type", None) == "text"])
            except Exception as retry_err:
                logger.error(f"Retry execution failed for MCP tool '{tool_name}': {retry_err}")
                return f"Error executing remote tool: {str(retry_err)}"

    async def _get_mcp_server_url(self, tenant_id: str, server_name: str, db_session=None) -> str | None:
        """Retrieves sse_url of a tenant's whitelisted server with Redis caching."""
        tenant_uuid = uuid.UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        
        # 1. Try Redis cache
        cache_key = f"{tenant_uuid}:config:mcp_servers"
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                servers = json.loads(cached_data)
                for s in servers:
                    if s.get("server_name") == server_name and s.get("is_active", True):
                        return s.get("sse_url")
        except Exception as cache_err:
            logger.warning(f"Redis cache lookup failed for MCP servers: {cache_err}")

        # 2. Query Postgres DB
        db_context = db_session
        if db_context is None:
            from db.database import SessionLocal
            db_context = SessionLocal()

        try:
            stmt = select(TenantMCPServer).where(
                TenantMCPServer.tenant_id == tenant_uuid,
                TenantMCPServer.server_name == server_name,
                TenantMCPServer.is_active == True
            )
            res = await db_context.execute(stmt)
            server_config = res.scalar_one_or_none()

            # Async fetch all active servers to repopulate cache
            stmt_all = select(TenantMCPServer).where(
                TenantMCPServer.tenant_id == tenant_uuid,
                TenantMCPServer.is_active == True
            )
            res_all = await db_context.execute(stmt_all)
            all_servers = res_all.scalars().all()
            cache_payload = [
                {"server_name": s.server_name, "sse_url": s.sse_url, "is_active": s.is_active}
                for s in all_servers
            ]
            try:
                await redis_client.setex(cache_key, 300, json.dumps(cache_payload))
            except Exception as cache_write_err:
                logger.warning(f"Failed to cache MCP servers to Redis: {cache_write_err}")

            if server_config:
                return server_config.sse_url
        except Exception as db_err:
            logger.error(f"Database query failed for TenantMCPServer: {db_err}")
        finally:
            if db_session is None:
                await db_context.close()
            
        return None

    async def _get_or_create_session(self, tenant_id: str, server_name: str, url: str, headers: Dict[str, str] = None) -> Any:
        key = (str(tenant_id), server_name)
        if key in self.sessions:
            return self.sessions[key]

        # Resolve headers to forward
        resolved_headers = headers
        if not resolved_headers:
            try:
                from api.deps import security_headers_ctx
                ctx_headers = security_headers_ctx.get()
                if ctx_headers:
                    # Forward security headers that are not None
                    resolved_headers = {k: v for k, v in ctx_headers.items() if v is not None}
            except Exception as ex:
                logger.debug(f"Failed to read security headers from ContextVar: {ex}")

        logger.info(f"Connecting to SSE MCP server '{server_name}' at {url} with headers: {resolved_headers}")

        exit_stack = AsyncExitStack()
        try:
            # We connect to SSE server via sse_client
            # Note that sse_client is an async context manager
            read_stream, write_stream = await exit_stack.enter_async_context(
                sse_client(url, headers=resolved_headers)
            )
            session = await exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            
            self.sessions[key] = session
            self.exit_stacks[key] = exit_stack
            logger.info(f"Established new SSE connection to MCP server '{server_name}' for tenant '{tenant_id}' at {url}")
            return session
        except Exception as conn_err:
            await exit_stack.aclose()
            logger.error(f"Failed to connect to SSE MCP server {server_name} at {url}: {conn_err}")
            raise conn_err

    async def _close_session(self, tenant_id: str, server_name: str):
        key = (str(tenant_id), server_name)
        session = self.sessions.pop(key, None)
        exit_stack = self.exit_stacks.pop(key, None)
        if exit_stack:
            try:
                await exit_stack.aclose()
                logger.info(f"Closed SSE session for MCP server '{server_name}' (Tenant: {tenant_id})")
            except Exception as close_err:
                logger.error(f"Error closing exit stack for '{server_name}': {close_err}")

    async def close_all(self):
        """Closes all active connection sessions in the pool."""
        logger.info("Closing all active MCP SSE sessions...")
        keys = list(self.sessions.keys())
        for tenant_id, server_name in keys:
            await self._close_session(tenant_id, server_name)

    def _mock_execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Mock fallback tool execution for testing and local environment sanity."""
        tenant_id = arguments.get("tenant_id")
        if server_name == "crm" and tool_name == "calculate_solar_roi":
            bill = arguments.get("monthly_bill", 2000000)
            area = arguments.get("roof_area_sqm", 30)
            zone = arguments.get("location_zone", "south")
            # Mock calculations
            system_size_kwp = round(area / 6.0, 1)
            est_cost_vnd = int(system_size_kwp * 15000000)
            est_generation_kwh = int(system_size_kwp * 4.2 * 30)
            monthly_savings_vnd = int(min(bill, est_generation_kwh * 2500))
            payback_years = round(est_cost_vnd / (monthly_savings_vnd * 12), 1) if monthly_savings_vnd > 0 else 99
            
            return json.dumps({
                "status": "success",
                "tenant_id": tenant_id,
                "system_size_kwp": system_size_kwp,
                "estimated_cost_vnd": est_cost_vnd,
                "estimated_monthly_generation_kwh": est_generation_kwh,
                "estimated_monthly_savings_vnd": monthly_savings_vnd,
                "payback_period_years": payback_years
            })
        elif server_name == "knowledge" and tool_name == "kb_search":
            return json.dumps({
                "status": "success",
                "tenant_id": tenant_id,
                "results": [
                    {"title": "Quy định mua bán điện mặt trời mái nhà", "score": 0.89, "content": "Solavie hỗ trợ đăng ký hợp đồng FIT mua bán điện với EVN..."}
                ]
            })
        elif server_name == "messaging" and tool_name == "send_message":
            return json.dumps({
                "status": "success",
                "tenant_id": tenant_id,
                "message_id": "mock_msg_9876",
                "details": f"Message sent to conversation {arguments.get('conversation_id')}"
            })
        
        return json.dumps({
            "status": "success",
            "server": server_name,
            "tool": tool_name,
            "tenant_id": tenant_id,
            "arguments": arguments,
            "note": "Mock response"
        })

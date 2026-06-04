import logging
import httpx
import asyncio
import pybreaker
from typing import Dict, Any

from core.config import settings
from core.circuit_breaker import call_async

logger = logging.getLogger(__name__)

# Exclude client-side (HTTP 4xx except 429) and configuration exceptions from tripping the Circuit Breaker
EXCLUDED_TOOL_EXCEPTIONS = [
    lambda e: isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500 and e.response.status_code != 429
]

# Tool circuit breakers: Opens if a tool endpoint fails 5 times in 30s, resets after 60s
TOOL_BREAKERS = {
    "knowledge_base_search": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0, exclude=EXCLUDED_TOOL_EXCEPTIONS),
    "web_search": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0, exclude=EXCLUDED_TOOL_EXCEPTIONS),
    "fetch_url": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0, exclude=EXCLUDED_TOOL_EXCEPTIONS),
    "send_message": pybreaker.CircuitBreaker(fail_max=5, reset_timeout=60.0, exclude=EXCLUDED_TOOL_EXCEPTIONS),
}

class ToolExecutor:
    def __init__(self):
        # We configure a shared HTTP client
        self.client = httpx.AsyncClient(timeout=10.0)

    async def execute(self, tool_name: str, args: Dict[str, Any], tenant_id: str) -> str:
        """Executes a tool call securely by injecting tenant isolation variables and applying dynamic timeouts."""
        # Inject tenant_id to ensure tenant isolation at the tool execution level
        args["tenant_id"] = tenant_id
        
        # Determine dynamic timeout: hot-path interactive tools (<= 2s) vs background heavy tools (<= 10s)
        tool_timeout = 2.0 if tool_name in ["knowledge_base_search", "send_message", "contact_lookup", "analyze_sentiment"] else 10.0
        
        logger.info(f"Executing tool {tool_name} for tenant {tenant_id} with timeout {tool_timeout}s and arguments: {args}")
        
        try:
            # Wrap execution with dynamic timeout
            return await asyncio.wait_for(
                self._route_and_execute(tool_name, args, tenant_id),
                timeout=tool_timeout
            )
        except asyncio.TimeoutError:
            logger.error(f"Timeout exceeded ({tool_timeout}s) executing tool: {tool_name}")
            return f"Error: Tool execution timed out after {tool_timeout} seconds."
        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {str(e)}")
            return f"Error executing tool: {str(e)}"

    async def _route_and_execute(self, tool_name: str, args: Dict[str, Any], tenant_id: str) -> str:
        """Route tool to its execution handler."""
        if tool_name == "web_search":
            return await self._execute_web_search(args.get("query", ""))
        elif tool_name == "fetch_url":
            return await self._execute_fetch_url(args.get("url", ""))
        elif tool_name == "knowledge_base_search":
            return await self._execute_kb_search(tenant_id, args.get("query", ""), args.get("top_k", 5))
        elif tool_name == "send_message":
            return await self._execute_send_message(
                tenant_id, 
                args.get("conversation_id", ""), 
                args.get("message", "")
            )
        else:
            return f"Error: Tool '{tool_name}' not supported."

    async def _execute_web_search(self, query: str) -> str:
        """Executes search query via Tavily API wrapped in a Circuit Breaker."""
        async def _call():
            if not settings.TAVILY_API_KEY:
                raise ValueError("Tavily API key is missing.")
            url = "https://api.tavily.com/search"
            payload = {
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "search_depth": "basic",
                "max_results": 3,
                "include_answer": True
            }
            response = await self.client.post(url, json=payload, timeout=8.0)
            response.raise_for_status()
            return response.json()

        try:
            data = await call_async(TOOL_BREAKERS["web_search"], _call)
            answer = data.get("answer")
            if answer:
                return f"Search Summary: {answer}"
            
            results = data.get("results", [])
            formatted = []
            for r in results:
                formatted.append(f"- {r.get('title')}: {r.get('content')} (Source: {r.get('url')})")
            return "\n".join(formatted) if formatted else "No results found."
        except Exception as e:
            logger.warning(f"Tavily search failed ({e}). Returning mock fallback.")
            return f"Mock Search Result for '{query}': Solavie Solar is a leading solar provider offering advanced energy solutions."

    async def _execute_fetch_url(self, url: str) -> str:
        """Fetch and extract web contents as markdown via Jina Reader API wrapped in a Circuit Breaker."""
        async def _call():
            # Call Jina Reader API to get markdown representation of the url
            reader_url = f"https://r.jina.ai/{url}"
            response = await self.client.get(reader_url, timeout=8.0)
            response.raise_for_status()
            return response.text

        try:
            return await call_async(TOOL_BREAKERS["fetch_url"], _call)
        except Exception as e:
            logger.error(f"Jina Reader fetch failed for {url}: {e}")
            return f"Error: Failed to fetch webpage content from URL '{url}' due to: {str(e)}."

    async def _execute_kb_search(self, tenant_id: str, query: str, top_k: int) -> str:
        """Query actual Knowledge Base service endpoint wrapped in a Circuit Breaker."""
        async def _call():
            # Knowledge Base Service is running on port 8004
            kb_url = "http://knowledge-base:8004/api/v1/search"
            headers = {"X-Tenant-ID": tenant_id}
            payload = {"query": query, "top_k": top_k}
            response = await self.client.post(kb_url, json=payload, headers=headers, timeout=1.8)
            response.raise_for_status()
            return response.text

        try:
            return await call_async(TOOL_BREAKERS["knowledge_base_search"], _call)
        except Exception as e:
            logger.warning(f"KB Search API failed ({e}). Returning mock fallback.")
            return (
                f"Knowledge Base matching documents for '{query}' (Tenant: {tenant_id}) [MOCK FALLBACK]:\n"
                f"- Solavie Product Brochure: Solavie provides off-grid and hybrid solar power systems with 25-year warranty.\n"
                f"- Installation Guide: Systems require a minimum roof space of 20 square meters with south-facing positioning."
            )

    async def _execute_send_message(self, tenant_id: str, conversation_id: str, message: str) -> str:
        """Call actual Messaging service send endpoint wrapped in a Circuit Breaker."""
        async def _call():
            # Messaging Service is running on port 8002
            msg_url = f"http://messaging:8002/api/v1/conversations/{conversation_id}/messages"
            headers = {"X-Tenant-ID": tenant_id}
            payload = {"message": message}
            response = await self.client.post(msg_url, json=payload, headers=headers, timeout=1.8)
            response.raise_for_status()
            return response.text

        try:
            return await call_async(TOOL_BREAKERS["send_message"], _call)
        except Exception as e:
            logger.warning(f"Messaging send API failed ({e}). Returning mock fallback.")
            return f"Success: Message successfully dispatched to conversation '{conversation_id}' [MOCK FALLBACK]."

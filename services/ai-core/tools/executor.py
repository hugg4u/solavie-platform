import logging
import httpx
from typing import Dict, Any

from core.config import settings

logger = logging.getLogger(__name__)

class ToolExecutor:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)

    async def execute(self, tool_name: str, args: Dict[str, Any], tenant_id: str) -> str:
        """Executes a tool call securely by injecting tenant isolation variables."""
        # Inject tenant_id to ensure tenant isolation at the tool execution level
        args["tenant_id"] = tenant_id
        
        logger.info(f"Executing tool {tool_name} for tenant {tenant_id} with arguments: {args}")
        
        try:
            if tool_name == "web_search":
                return await self._execute_web_search(args.get("query", ""))
            elif tool_name == "knowledge_base_search":
                return await self._execute_kb_search(tenant_id, args.get("query", ""))
            elif tool_name == "send_message":
                return await self._execute_send_message(
                    tenant_id, 
                    args.get("conversation_id", ""), 
                    args.get("message", "")
                )
            else:
                return f"Error: Tool '{tool_name}' not supported."
        except Exception as e:
            logger.error(f"Failed to execute tool {tool_name}: {str(e)}")
            return f"Error executing tool: {str(e)}"

    async def _execute_web_search(self, query: str) -> str:
        """Executes search query via Tavily API."""
        if not settings.TAVILY_API_KEY:
            logger.warning("Tavily API key is missing. Returning mock web search results.")
            return f"Mock Search Result for '{query}': Solavie Solar is a leading solar provider offering advanced energy solutions."

        url = "https://api.tavily.com/search"
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": query,
            "search_depth": "basic",
            "max_results": 3,
            "include_answer": True
        }
        
        try:
            response = await self.client.post(url, json=payload, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                answer = data.get("answer")
                if answer:
                    return f"Search Summary: {answer}"
                
                results = data.get("results", [])
                formatted = []
                for r in results:
                    formatted.append(f"- {r.get('title')}: {r.get('content')} (Source: {r.get('url')})")
                return "\n".join(formatted) if formatted else "No results found."
            else:
                return f"Error from Search API: {response.status_code} - {response.text}"
        except Exception as e:
            logger.error(f"Tavily search request failed: {e}")
            raise

    async def _execute_kb_search(self, tenant_id: str, query: str) -> str:
        """Mock/Actual HTTP request to Knowledge Base service."""
        # Under real deployment, it would call: http://knowledge-base:8000/api/v1/search
        # We simulate a response containing tenant-specific knowledge.
        logger.info(f"Simulating Knowledge Base search for tenant {tenant_id}")
        return (
            f"Knowledge Base matching documents for '{query}' (Tenant: {tenant_id}):\n"
            f"- Solavie Product Brochure: Solavie provides off-grid and hybrid solar power systems with 25-year warranty.\n"
            f"- Installation Guide: Systems require a minimum roof space of 20 square meters with south-facing positioning."
        )

    async def _execute_send_message(self, tenant_id: str, conversation_id: str, message: str) -> str:
        """Mock/Actual HTTP request to Messaging service."""
        # Under real deployment, it would call: http://messaging:8000/api/v1/send
        logger.info(f"Simulating sending message to conversation {conversation_id} (Tenant: {tenant_id})")
        return f"Success: Message successfully dispatched to conversation '{conversation_id}'."

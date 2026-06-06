import pytest
import uuid
import json
from unittest.mock import AsyncMock, patch, MagicMock

from gateway.mcp.manager import MCPClientManager
from db.models import TenantMCPServer
from tools.executor import ToolExecutor

class MockTextContent:
    def __init__(self, text):
        self.type = "text"
        self.text = text

class MockResult:
    def __init__(self, scalar_val, all_val):
        self._scalar_val = scalar_val
        self._all_val = all_val
        
    def scalar_one_or_none(self):
        return self._scalar_val
        
    def scalars(self):
        return self
        
    def all(self):
        return self._all_val

@pytest.fixture
def client_manager():
    manager = MCPClientManager()
    manager.sessions.clear()
    manager.exit_stacks.clear()
    return manager

@pytest.mark.asyncio
async def test_mcp_ssrf_prevention(client_manager):
    # Setup test data
    tenant_id = str(uuid.uuid4())
    
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult(None, [])
    
    # Executing for a non-whitelisted server
    result = await client_manager.execute_mcp_tool(
        tenant_id=tenant_id,
        full_tool_name="crm__calculate_solar_roi",
        arguments={"monthly_bill": 1000000},
        db_session=mock_db
    )
    
    assert "not whitelisted" in result or "inactive" in result
    
@pytest.mark.asyncio
async def test_mcp_whitelisted_execution(client_manager):
    tenant_id = str(uuid.uuid4())
    server_name = "crm"
    sse_url = "http://crm:8003/api/v1/crm/mcp"
    
    mock_server = TenantMCPServer(
        tenant_id=uuid.UUID(tenant_id),
        server_name=server_name,
        sse_url=sse_url,
        is_active=True
    )
    
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult(mock_server, [mock_server])
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.content = [MockTextContent("solar roi calculation successful")]
    mock_session.call_tool.return_value = mock_result
    
    with patch.object(client_manager, '_get_or_create_session', return_value=mock_session), \
         patch("gateway.mcp.manager.MCP_AVAILABLE", True):
         
        result = await client_manager.execute_mcp_tool(
            tenant_id=tenant_id,
            full_tool_name="crm__calculate_solar_roi",
            arguments={"monthly_bill": 1000000, "roof_area_sqm": 25},
            db_session=mock_db
        )
        
        assert result == "solar roi calculation successful"
        mock_session.call_tool.assert_called_once()
        args_passed = mock_session.call_tool.call_args[0][1]
        assert args_passed["tenant_id"] == tenant_id

@pytest.mark.asyncio
async def test_mcp_tenant_id_override(client_manager):
    tenant_id = str(uuid.uuid4())
    fake_tenant_id = str(uuid.uuid4())
    
    mock_server = TenantMCPServer(
        tenant_id=uuid.UUID(tenant_id),
        server_name="crm",
        sse_url="http://crm:8003/api/v1/crm/mcp",
        is_active=True
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult(mock_server, [mock_server])
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.content = [MockTextContent("ok")]
    mock_session.call_tool.return_value = mock_result
    
    with patch.object(client_manager, '_get_or_create_session', return_value=mock_session), \
         patch("gateway.mcp.manager.MCP_AVAILABLE", True):
         
        await client_manager.execute_mcp_tool(
            tenant_id=tenant_id,
            full_tool_name="crm__calculate_solar_roi",
            arguments={"tenant_id": fake_tenant_id, "monthly_bill": 1000000},
            db_session=mock_db
        )
        
        args_passed = mock_session.call_tool.call_args[0][1]
        assert args_passed["tenant_id"] == tenant_id

@pytest.mark.asyncio
async def test_mcp_path_traversal_sanitation(client_manager):
    tenant_id = str(uuid.uuid4())
    
    mock_server = TenantMCPServer(
        tenant_id=uuid.UUID(tenant_id),
        server_name="crm",
        sse_url="http://crm:8003/api/v1/crm/mcp",
        is_active=True
    )
    mock_db = AsyncMock()
    mock_db.execute.return_value = MockResult(mock_server, [mock_server])
    
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.content = [MockTextContent("ok")]
    mock_session.call_tool.return_value = mock_result
    
    with patch.object(client_manager, '_get_or_create_session', return_value=mock_session), \
         patch("gateway.mcp.manager.MCP_AVAILABLE", True):
         
        await client_manager.execute_mcp_tool(
            tenant_id=tenant_id,
            full_tool_name="crm__calculate_solar_roi",
            arguments={"file_path": "../etc/passwd", "other_path": "folder\\..\\secret.txt"},
            db_session=mock_db
        )
        
        args_passed = mock_session.call_tool.call_args[0][1]
        assert args_passed["file_path"] == "etc/passwd"
        assert args_passed["other_path"] == "folder\\secret.txt"

@pytest.mark.asyncio
async def test_tool_executor_routes_to_mcp():
    executor = ToolExecutor()
    tenant_id = str(uuid.uuid4())
    
    mock_result = "mcp search results"
    with patch.object(executor.mcp_manager, 'execute_mcp_tool', return_value=mock_result) as mock_mcp:
        result = await executor.execute(
            tool_name="knowledge_base_search",
            args={"query": "solar pricing"},
            tenant_id=tenant_id
        )
        
        assert result == mock_result
        mock_mcp.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="knowledge__kb_search",
            arguments={"query": "solar pricing", "tenant_id": tenant_id}
        )

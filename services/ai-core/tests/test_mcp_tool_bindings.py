import pytest
import uuid
from unittest.mock import AsyncMock, patch
from tools.registry import ToolPermissionManager, PERMISSION_MATRIX, TOOL_PERMISSIONS
from tools.executor import ToolExecutor, TOOL_BREAKERS

def test_mcp_matrix_chatbot_authorized():
    pm = ToolPermissionManager()
    new_tools = [
        "calculate_solar_roi",
        "get_proposal_preview",
        "create_om_ticket",
        "get_ticket_status",
        "create_lead_deal",
        "update_deal_stage"
    ]
    for tool in new_tools:
        assert pm.is_tool_allowed("chatbot", tool) is True, f"{tool} should be allowed for chatbot use_case"

def test_mcp_tool_breakers_registered():
    new_tools = [
        "calculate_solar_roi",
        "get_proposal_preview",
        "create_om_ticket",
        "get_ticket_status",
        "create_lead_deal",
        "update_deal_stage"
    ]
    for tool in new_tools:
        assert tool in TOOL_BREAKERS, f"Circuit breaker for {tool} should be registered"
        assert TOOL_BREAKERS[tool].fail_max == 5
        assert TOOL_BREAKERS[tool].reset_timeout == 60.0

@pytest.mark.asyncio
async def test_rbac_user_authorization_success():
    pm = ToolPermissionManager()
    tenant_id = str(uuid.uuid4())
    
    # Mock Redis to return standard user permissions containing crm scopes
    mock_perms = [
        "crm:deals:read",
        "crm:deals:create",
        "crm:deals:update",
        "crm:tickets:create",
        "crm:tickets:read"
    ]
    
    with patch("tools.registry.redis_client") as mock_redis:
        mock_redis.get = AsyncMock(return_value=None)  # Cache miss, falls back to in-memory check
        
        # Testing fallback role (manager/standard_user should have these permissions now)
        assert await pm.is_user_authorized(tenant_id, "manager", "calculate_solar_roi") is True
        assert await pm.is_user_authorized(tenant_id, "manager", "create_lead_deal") is True
        assert await pm.is_user_authorized(tenant_id, "manager", "create_om_ticket") is True
        
        # Visitor role should NOT have these permissions
        assert await pm.is_user_authorized(tenant_id, "visitor", "calculate_solar_roi") is False
        assert await pm.is_user_authorized(tenant_id, "visitor", "create_lead_deal") is False

@pytest.mark.asyncio
async def test_mcp_mapping_correctness():
    executor = ToolExecutor()
    tenant_id = str(uuid.uuid4())
    
    # We verify that calling execute for each tool routes to the correct MCP tool name
    # calculate_solar_roi -> solar_calc__calculate_solar_roi
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="calculate_solar_roi",
            args={"monthly_bill": 1500000, "roof_area_sqm": 40, "location_zone": "south"},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="solar_calc__calculate_solar_roi",
            arguments={
                "monthly_bill": 1500000, 
                "roof_area_sqm": 40, 
                "location_zone": "south",
                "tenant_id": tenant_id
            }
        )

    # get_proposal_preview -> solar_calc__get_proposal_preview
    deal_uuid = str(uuid.uuid4())
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="get_proposal_preview",
            args={"deal_id": deal_uuid},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="solar_calc__get_proposal_preview",
            arguments={
                "deal_id": deal_uuid,
                "tenant_id": tenant_id
            }
        )

    # create_om_ticket -> om_ticket__create_om_ticket
    contact_uuid = str(uuid.uuid4())
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="create_om_ticket",
            args={"contact_id": contact_uuid, "title": "Inverter error", "description": "Red light blinking"},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="om_ticket__create_om_ticket",
            arguments={
                "contact_id": contact_uuid,
                "title": "Inverter error",
                "description": "Red light blinking",
                "tenant_id": tenant_id
            }
        )

    # get_ticket_status -> om_ticket__get_ticket_status
    ticket_uuid = str(uuid.uuid4())
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="get_ticket_status",
            args={"ticket_id": ticket_uuid},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="om_ticket__get_ticket_status",
            arguments={
                "ticket_id": ticket_uuid,
                "tenant_id": tenant_id
            }
        )

    # create_lead_deal -> crm__create_lead_deal
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="create_lead_deal",
            args={"contact_id": contact_uuid, "deal_name": "Solar Project A"},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="crm__create_lead_deal",
            arguments={
                "contact_id": contact_uuid,
                "deal_name": "Solar Project A",
                "tenant_id": tenant_id
            }
        )

    # update_deal_stage -> crm__update_deal_stage
    deal_uuid2 = str(uuid.uuid4())
    with patch.object(executor.mcp_manager, "execute_mcp_tool", AsyncMock(return_value="mock_val")) as mock_execute:
        await executor.execute(
            tool_name="update_deal_stage",
            args={"deal_id": deal_uuid2, "stage": "proposal"},
            tenant_id=tenant_id
        )
        mock_execute.assert_called_once_with(
            tenant_id=tenant_id,
            full_tool_name="crm__update_deal_stage",
            arguments={
                "deal_id": deal_uuid2,
                "stage": "proposal",
                "tenant_id": tenant_id
            }
        )

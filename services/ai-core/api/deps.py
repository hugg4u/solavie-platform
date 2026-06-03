import uuid
from fastapi import Header, HTTPException
from gateway.router import safe_uuid
from db.database import get_db

def get_effective_tenant(
    x_tenant_id: str | None = Header(None),
    client_tenant_id: str | None = None
) -> uuid.UUID:
    """
    Enforce tenant isolation by prioritizing X-Tenant-ID header injected by Kong Gateway
    over any client-supplied tenant_id. Returns UUID.
    """
    tenant_id = x_tenant_id or client_tenant_id
    if not tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-ID header or tenant_id is required.")
    tenant_uuid = safe_uuid(tenant_id)
    if not tenant_uuid:
        raise HTTPException(status_code=400, detail="Invalid tenant_id UUID format.")
    return tenant_uuid

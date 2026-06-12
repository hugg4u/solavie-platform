import uuid
import hmac
import hashlib
import os
from contextvars import ContextVar
from fastapi import Header, HTTPException
from gateway.router import safe_uuid
from db.database import get_db

# Context variable to forward security headers across thread/task boundary to MCP client
security_headers_ctx: ContextVar[dict | None] = ContextVar("security_headers", default=None)

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

def check_permission(user_permissions: set[str], required_perm: str) -> bool:
    """
    Check if the user has the required permission, supporting wildcards:
    - '*' -> matches all
    - 'service:*' -> matches any permission on that service
    - 'service:resource:*' -> matches any action on that resource
    """
    if "*" in user_permissions:
        return True
    if required_perm in user_permissions:
        return True
    
    parts = required_perm.split(":")
    if len(parts) == 3:
        service, resource, action = parts
        if f"{service}:*" in user_permissions:
            return True
        if f"{service}:{resource}:*" in user_permissions:
            return True
            
    return False

def require_permission(required_permission: str):
    """
    FastAPI dependency factory to verify Gateway-signed permissions and enforce RBAC.
    """
    def dependency(
        x_tenant_id: str | None = Header(None),
        x_user_id: str | None = Header(None),
        x_user_permissions: str | None = Header(None),
        x_permissions_signature: str | None = Header(None)
    ) -> str:
        # Check if headers exist
        if not x_tenant_id or not x_user_id or x_user_permissions is None or not x_permissions_signature:
            raise HTTPException(status_code=403, detail="Missing required authorization headers or signature.")
        
        # Verify HMAC signature
        secret = os.getenv("GATEWAY_SIGNING_SECRET", "default-gateway-signing-secret-key-change-me-in-production")
        payload = f"{x_tenant_id}:{x_user_id}:{x_user_permissions}"
        expected_sig = hmac.new(secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        
        if not hmac.compare_digest(x_permissions_signature, expected_sig):
            raise HTTPException(status_code=403, detail="Invalid authorization signature.")
            
        # Store security headers in ContextVar for propagation to MCP client
        headers = {
            "X-Tenant-ID": x_tenant_id,
            "X-User-ID": x_user_id,
            "X-User-Permissions": x_user_permissions,
            "X-Permissions-Signature": x_permissions_signature
        }
        security_headers_ctx.set(headers)

        # Match permissions
        perms = set(p.strip() for p in x_user_permissions.split(",") if p.strip())
        if check_permission(perms, required_permission):
            return x_user_permissions
            
        raise HTTPException(status_code=403, detail=f"Forbidden: requires permission '{required_permission}'.")
    return dependency



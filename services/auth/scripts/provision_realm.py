#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
import secrets
import string
import time
import requests

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "category": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger("solavie.auth.provisioner")

def generate_secret(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def wait_for_keycloak(keycloak_url, timeout=60):
    url = f"{keycloak_url.rstrip('/')}/health/ready"
    start_time = time.time()
    logger.info(f"Waiting for Keycloak to become ready at: {url}")
    while True:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                logger.info("Keycloak is ready!")
                return True
        except Exception:
            pass
        if time.time() - start_time > timeout:
            raise TimeoutError("Timed out waiting for Keycloak to start up and become ready.")
        time.sleep(2)

def get_admin_token(keycloak_url, admin_username, admin_password):
    url = f"{keycloak_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": admin_username,
        "password": admin_password,
        "grant_type": "password"
    }
    try:
        response = requests.post(url, data=data, timeout=10)
        response.raise_for_status()
        return response.json()["access_token"]
    except Exception as e:
        logger.error(f"Failed to authenticate admin user against master realm: {str(e)}")
        raise

def check_realm_exists(keycloak_url, admin_token, realm_name):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers, timeout=10)
    return response.status_code == 200

def create_realm(keycloak_url, admin_token, realm_template_path, tenant_id, tenant_name, api_gateway_secret, user_service_secret):
    url = f"{keycloak_url.rstrip('/')}/admin/realms"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    # Load and render template
    if not os.path.exists(realm_template_path):
        raise FileNotFoundError(f"Template not found at: {realm_template_path}")
        
    with open(realm_template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
        
    # Replacements
    rendered_content = template_content\
        .replace("{{tenant_id}}", tenant_id)\
        .replace("{{tenant_name}}", tenant_name)\
        .replace("{{api_gateway_secret}}", api_gateway_secret)\
        .replace("{{user_service_secret}}", user_service_secret)
        
    realm_data = json.loads(rendered_content)
    
    try:
        response = requests.post(url, headers=headers, json=realm_data, timeout=10)
        if response.status_code == 201:
            logger.info(f"Successfully created Keycloak realm: {tenant_id}")
        else:
            logger.error(f"Failed to create realm. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error occurred during realm creation POST request: {str(e)}")
        raise

def create_admin_user(keycloak_url, admin_token, realm_name, admin_email, admin_password, tenant_name="Solavie"):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    # Keycloak 24+ enables User Profile by default, requiring firstName and lastName.
    # Without them, the account is marked as "not fully set up" and password grant fails.
    user_payload = {
        "username": "admin",
        "email": admin_email,
        "firstName": "Tenant",
        "lastName": "Admin",
        "enabled": True,
        "emailVerified": True,
        "requiredActions": [],
        "credentials": [
            {
                "type": "password",
                "value": admin_password,
                "temporary": False
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=user_payload, timeout=10)
        if response.status_code == 201:
            logger.info(f"Successfully created tenant admin user 'admin' in realm: {realm_name}")
            return response.headers.get("Location")
        else:
            logger.error(f"Failed to create admin user. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error occurred during user creation POST request: {str(e)}")
        raise

def get_user_id_by_username(keycloak_url, admin_token, realm_name, username):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }
    params = {
        "username": username
    }
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    users = response.json()
    if not users:
        raise ValueError(f"User '{username}' not found in realm '{realm_name}'")
    return users[0]["id"]

def assign_role_to_user(keycloak_url, admin_token, realm_name, user_id, role_name):
    # Fetch role representation
    role_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/roles/{role_name}"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(role_url, headers=headers, timeout=10)
    response.raise_for_status()
    role_rep = response.json()
    
    # Assign role to user
    assign_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm"
    payload = [role_rep]
    
    assign_response = requests.post(assign_url, headers=headers, json=payload, timeout=10)
    assign_response.raise_for_status()
    logger.info(f"Assigned role '{role_name}' to user ID '{user_id}' in realm: {realm_name}")

def create_custom_client_scopes(keycloak_url, admin_token, realm_name):
    scopes = [
        "campaign", "crm", "chatbot", "content", "messaging", "analytics", 
        "ai-core", "tenant-config", "dms", "link-shortener", "scheduler", 
        "comment-manager", "notification", "channel-connector", 
        "media-processor", "knowledge-base", "observability"
    ]
    
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    # Get Client UUIDs for dashboard and api-gateway
    clients_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/clients"
    try:
        clients_resp = requests.get(clients_url, headers=headers, timeout=10)
        clients_resp.raise_for_status()
        clients_list = clients_resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch clients from realm {realm_name}: {e}")
        return
    
    dashboard_uuid = None
    api_gateway_uuid = None
    for c in clients_list:
        if c["clientId"] == "dashboard":
            dashboard_uuid = c["id"]
        elif c["clientId"] == "api-gateway":
            api_gateway_uuid = c["id"]
            
    if not dashboard_uuid or not api_gateway_uuid:
        logger.error(f"Failed to find dashboard or api-gateway clients in realm: {realm_name}")
        return
        
    for scope_name in scopes:
        # Create client scope
        scope_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/client-scopes"
        scope_payload = {
            "name": scope_name,
            "description": f"Access to {scope_name.capitalize()} Service APIs",
            "protocol": "openid-connect",
            "attributes": {
                "display.on.consent.screen": "true",
                "include.in.token.scope": "true"
            }
        }
        try:
            resp = requests.post(scope_url, headers=headers, json=scope_payload, timeout=10)
            if resp.status_code == 201:
                logger.info(f"Created custom client scope: {scope_name}")
            elif resp.status_code == 409:
                logger.info(f"Client scope already exists: {scope_name}")
            else:
                logger.warning(f"Failed to create client scope {scope_name}: {resp.text}")
                continue
        except Exception as e:
            logger.error(f"Error creating client scope {scope_name}: {e}")
            continue
            
        # Get client scope ID
        try:
            get_scope_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/client-scopes"
            scopes_resp = requests.get(get_scope_url, headers=headers, timeout=10)
            scopes_resp.raise_for_status()
            scope_id = None
            for s in scopes_resp.json():
                if s["name"] == scope_name:
                    scope_id = s["id"]
                    break
            if not scope_id:
                logger.error(f"Scope {scope_name} not found after creation.")
                continue
                
            # Assign as optional client scope to dashboard and api-gateway
            for client_uuid in [dashboard_uuid, api_gateway_uuid]:
                assoc_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/clients/{client_uuid}/optional-client-scopes/{scope_id}"
                assoc_resp = requests.put(assoc_url, headers=headers, timeout=10)
                if assoc_resp.status_code in [204, 201, 200]:
                    logger.info(f"Assigned scope {scope_name} to client UUID {client_uuid}")
                else:
                    logger.warning(f"Failed to assign scope {scope_name} to client UUID {client_uuid}: {assoc_resp.text}")
        except Exception as e:
            logger.error(f"Error assigning client scope {scope_name}: {e}")

def provision_user_service_client(keycloak_url, admin_token, realm_name, user_service_secret):
    """
    AC 4.7 / Requirement 5.4:
    Cấu hình Client Credentials cho User Service.
    Gán role 'manage-users' từ 'realm-management' cho service account của user-service-client.
    Áp dụng nguyên tắc Least Privilege — không gán admin của master realm.
    """
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    base_url = keycloak_url.rstrip('/')

    # 1. Lấy ID của client user-service-client trong realm
    clients_url = f"{base_url}/admin/realms/{realm_name}/clients"
    try:
        resp = requests.get(clients_url, headers=headers, timeout=10)
        resp.raise_for_status()
        clients_list = resp.json()
    except Exception as e:
        logger.error(f"[user-service-client] Failed to fetch clients from realm {realm_name}: {e}")
        return

    user_svc_client_id = None
    realm_mgmt_client_id = None
    for c in clients_list:
        if c["clientId"] == "user-service-client":
            user_svc_client_id = c["id"]
        elif c["clientId"] == "realm-management":
            realm_mgmt_client_id = c["id"]

    if not user_svc_client_id:
        logger.error(f"[user-service-client] 'user-service-client' not found in realm {realm_name}")
        return
    if not realm_mgmt_client_id:
        logger.error(f"[user-service-client] 'realm-management' client not found in realm {realm_name}")
        return

    # 2. Lấy service account user ID của user-service-client
    sa_url = f"{base_url}/admin/realms/{realm_name}/clients/{user_svc_client_id}/service-account-user"
    try:
        sa_resp = requests.get(sa_url, headers=headers, timeout=10)
        sa_resp.raise_for_status()
        sa_user_id = sa_resp.json()["id"]
        logger.info(f"[user-service-client] Service account user ID: {sa_user_id}")
    except Exception as e:
        logger.error(f"[user-service-client] Failed to get service account user: {e}")
        return

    # 3. Lấy role 'manage-users' từ realm-management client roles
    role_url = f"{base_url}/admin/realms/{realm_name}/clients/{realm_mgmt_client_id}/roles/manage-users"
    try:
        role_resp = requests.get(role_url, headers=headers, timeout=10)
        role_resp.raise_for_status()
        manage_users_role = role_resp.json()
        logger.info(f"[user-service-client] Found 'manage-users' role: {manage_users_role['id']}")
    except Exception as e:
        logger.error(f"[user-service-client] Failed to get 'manage-users' role from realm-management: {e}")
        return

    # 4. Gán role 'manage-users' cho service account (Least Privilege)
    assign_url = f"{base_url}/admin/realms/{realm_name}/users/{sa_user_id}/role-mappings/clients/{realm_mgmt_client_id}"
    try:
        assign_resp = requests.post(assign_url, headers=headers, json=[manage_users_role], timeout=10)
        if assign_resp.status_code in [204, 200, 201]:
            logger.info(f"[user-service-client] Successfully assigned 'manage-users' role to service account in realm: {realm_name}")
        else:
            logger.error(f"[user-service-client] Failed to assign role. Status: {assign_resp.status_code}, Body: {assign_resp.text}")
    except Exception as e:
        logger.error(f"[user-service-client] Error assigning manage-users role: {e}")


def main():
    parser = argparse.ArgumentParser(description="Provision a new Keycloak realm for Solavie multi-tenancy.")
    parser.add_argument("--keycloak-url", default=os.getenv("KEYCLOAK_URL", "http://localhost:8081"), help="Keycloak server URL")
    parser.add_argument("--admin-username", default=os.getenv("KC_ADMIN", "admin"), help="Master admin username")
    parser.add_argument("--admin-password", default=os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass"), help="Master admin password")
    parser.add_argument("--template-path", default=os.path.join(os.path.dirname(__file__), "../templates/tenant-realm-template.json"), help="Path to realm config template")
    parser.add_argument("--tenant-id", required=True, help="Unique Tenant identifier (used as realm name, e.g. tenant-a-uuid)")
    parser.add_argument("--tenant-name", required=True, help="Display name of the tenant")
    parser.add_argument("--admin-email", required=True, help="Tenant admin email address")
    parser.add_argument("--admin-password-user", default="SolavieSecurePass123!", help="Tenant admin user password")
    parser.add_argument("--api-gateway-secret", help="Secret key for api-gateway confidential client (auto-generated if empty)")
    parser.add_argument("--user-service-secret", help="Secret key for user-service-client (auto-generated if empty)")
    parser.add_argument("--force", action="store_true", help="Delete and recreate realm if it already exists")
    
    args = parser.parse_args()
    
    tenant_id = args.tenant_id.lower().strip()
    api_gateway_secret = args.api_gateway_secret or generate_secret()
    user_service_secret = args.user_service_secret or generate_secret()
    
    try:
        # Wait for Keycloak to be healthy first
        wait_for_keycloak(args.keycloak_url)
        
        logger.info(f"Starting realm provisioning process for tenant: {tenant_id} ({args.tenant_name})")
        
        # 1. Fetch admin access token from master realm
        logger.info("Retrieving master admin access token...")
        admin_token = get_admin_token(args.keycloak_url, args.admin_username, args.admin_password)
        
        # 2. Check if realm already exists
        if check_realm_exists(args.keycloak_url, admin_token, tenant_id):
            if args.force:
                logger.info(f"Realm '{tenant_id}' already exists. Deleting it due to --force flag...")
                delete_url = f"{args.keycloak_url.rstrip('/')}/admin/realms/{tenant_id}"
                del_resp = requests.delete(delete_url, headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
                del_resp.raise_for_status()
                logger.info(f"Deleted realm '{tenant_id}'. Proceeding with fresh creation.")
            else:
                logger.warning(f"Realm '{tenant_id}' already exists. Skipping realm creation.")
                sys.exit(0)
            
        # 3. Create realm using template
        logger.info(f"Creating realm '{tenant_id}' from template...")
        create_realm(args.keycloak_url, admin_token, args.template_path, tenant_id, args.tenant_name, api_gateway_secret, user_service_secret)
        
        # 4. Create first admin user
        logger.info(f"Creating tenant admin user 'admin' for realm '{tenant_id}'...")
        create_admin_user(args.keycloak_url, admin_token, tenant_id, args.admin_email, args.admin_password_user, args.tenant_name)
        
        # 5. Fetch user ID and assign 'Admin' role
        logger.info("Resolving user ID and mapping 'Admin' realm role...")
        user_id = get_user_id_by_username(args.keycloak_url, admin_token, tenant_id, "admin")
        assign_role_to_user(args.keycloak_url, admin_token, tenant_id, user_id, "Admin")
        
        # 5.5 Create and assign custom client scopes
        logger.info("Creating and assigning custom business client scopes...")
        create_custom_client_scopes(args.keycloak_url, admin_token, tenant_id)
        
        # 5.6 Configure user-service-client: grant manage-users role (AC 4.7 / Req 5.4)
        logger.info("Configuring user-service-client with Least Privilege (manage-users role)...")
        provision_user_service_client(args.keycloak_url, admin_token, tenant_id, user_service_secret)
        
        # 6. Complete provisioning output
        logger.info(f"Realm provisioning successfully completed for: {tenant_id}")
        
        output = {
            "status": "success",
            "tenant_id": tenant_id,
            "tenant_name": args.tenant_name,
            "discovery_url": f"{args.keycloak_url.rstrip('/')}/realms/{tenant_id}/.well-known/openid-configuration",
            "clients": {
                "dashboard": {
                    "client_id": "dashboard",
                    "type": "public"
                },
                "api-gateway": {
                    "client_id": "api-gateway",
                    "type": "confidential",
                    "secret": api_gateway_secret
                },
                "user-service-client": {
                    "client_id": "user-service-client",
                    "type": "confidential",
                    "secret": user_service_secret,
                    "roles": ["manage-users"]
                }
            },
            "admin_user": {
                "username": "admin",
                "email": args.admin_email,
                "role": "Admin"
            }
        }
        
        print("\nPROVISION_OUTPUT_START")
        print(json.dumps(output, indent=2))
        print("PROVISION_OUTPUT_END\n")
        
    except Exception as e:
        logger.critical(f"Realm provisioning failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

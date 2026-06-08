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
logger = logging.getLogger("solavie.auth.org_provisioner")

def generate_secret(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def wait_for_keycloak(keycloak_url, timeout=60):
    from urllib.parse import urlparse
    parsed = urlparse(keycloak_url)
    
    urls_to_try = []
    if parsed.hostname:
        scheme = parsed.scheme or "http"
        urls_to_try.append(f"{scheme}://{parsed.hostname}:9000/health/ready")
    urls_to_try.append(f"{keycloak_url.rstrip('/')}/health/ready")
    
    start_time = time.time()
    logger.info(f"Waiting for Keycloak to become ready (trying URLs: {', '.join(urls_to_try)})")
    while True:
        for url in urls_to_try:
            try:
                response = requests.get(url, timeout=2)
                if response.status_code == 200:
                    logger.info(f"Keycloak is ready! (health checked at {url})")
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

def create_shared_realm(keycloak_url, admin_token, realm_template_path, api_gateway_secret, user_service_secret):
    url = f"{keycloak_url.rstrip('/')}/admin/realms"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    if not os.path.exists(realm_template_path):
        raise FileNotFoundError(f"Template not found at: {realm_template_path}")
        
    with open(realm_template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
        
    rendered_content = template_content\
        .replace("{{api_gateway_secret}}", api_gateway_secret)\
        .replace("{{user_service_secret}}", user_service_secret)
        
    realm_data = json.loads(rendered_content)
    
    try:
        response = requests.post(url, headers=headers, json=realm_data, timeout=10)
        if response.status_code == 201:
            logger.info("Successfully created Keycloak shared realm 'solavie'")
        else:
            logger.error(f"Failed to create shared realm. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error occurred during shared realm creation POST request: {str(e)}")
        raise

def get_organization_id(keycloak_url, admin_token, realm_name, alias):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    orgs = response.json()
    for org in orgs:
        if org.get("alias") == alias:
            return org.get("id")
    return None

def create_organization(keycloak_url, admin_token, realm_name, tenant_id, company_name, admin_email):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    domain = "solavie.com"
    if admin_email and "@" in admin_email:
        parts = admin_email.split("@")
        if len(parts) == 2:
            domain = parts[1]
            
    org_payload = {
        "name": company_name,
        "alias": tenant_id,
        "enabled": True,
        "domains": [
            {
                "name": domain,
                "verified": True
            }
        ],
        "attributes": {
            "tenant_id": [tenant_id]
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=org_payload, timeout=10)
        if response.status_code == 201:
            logger.info(f"Successfully created Organization '{company_name}' (alias: {tenant_id}) with domain: {domain}")
            location = response.headers.get("Location")
            if location:
                org_id = location.split("/")[-1]
                return org_id
            # Fallback if Location is missing
            return get_organization_id(keycloak_url, admin_token, realm_name, tenant_id)
        else:
            logger.error(f"Failed to create Organization. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error occurred during Organization creation: {str(e)}")
        raise



def create_org_user(keycloak_url, admin_token, realm_name, tenant_id, admin_email, admin_password_user):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    username = f"admin-{tenant_id}"
    user_payload = {
        "username": username,
        "email": admin_email,
        "firstName": "Tenant",
        "lastName": "Admin",
        "enabled": True,
        "emailVerified": True,
        "requiredActions": [],
        "credentials": [
            {
                "type": "password",
                "value": admin_password_user,
                "temporary": False
            }
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=user_payload, timeout=10)
        if response.status_code == 201:
            logger.info(f"Successfully created user '{username}' in realm: {realm_name}")
            location = response.headers.get("Location")
            if location:
                return location.split("/")[-1]
            # Fallback
            user_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
            user_resp = requests.get(user_url, headers=headers, params={"username": username}, timeout=10)
            user_resp.raise_for_status()
            users = user_resp.json()
            if users:
                return users[0]["id"]
            raise ValueError(f"Could not find created user ID for '{username}'")
        else:
            logger.error(f"Failed to create user. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error occurred during user creation: {str(e)}")
        raise

def add_member_to_org(keycloak_url, admin_token, realm_name, org_id, user_id):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations/{org_id}/members"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    # Payload is user_id as a raw JSON string
    try:
        response = requests.post(url, headers=headers, json=user_id, timeout=10)
        if response.status_code in [204, 201, 200]:
            logger.info(f"Successfully added user ID '{user_id}' to Org ID '{org_id}'")
        else:
            logger.error(f"Failed to add user to organization. Status: {response.status_code}, Body: {response.text}")
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Error adding member to organization: {e}")
        raise

def assign_realm_role_to_user(keycloak_url, admin_token, realm_name, user_id, role_name):
    role_name_cap = role_name.capitalize()
    role_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/roles/{role_name_cap}"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
    response = requests.get(role_url, headers=headers, timeout=10)
    response.raise_for_status()
    role_rep = response.json()
    
    assign_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm"
    assign_response = requests.post(assign_url, headers=headers, json=[role_rep], timeout=10)
    assign_response.raise_for_status()
    logger.info(f"Assigned realm role '{role_name_cap}' to user ID '{user_id}' in realm: {realm_name}")

def create_custom_client_scopes_solavie(keycloak_url, admin_token, realm_name):
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
                
            for client_uuid in [dashboard_uuid, api_gateway_uuid]:
                assoc_url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/clients/{client_uuid}/optional-client-scopes/{scope_id}"
                assoc_resp = requests.put(assoc_url, headers=headers, timeout=10)
                if assoc_resp.status_code in [204, 201, 200]:
                    logger.info(f"Assigned scope {scope_name} to client UUID {client_uuid}")
                else:
                    logger.warning(f"Failed to assign scope {scope_name} to client UUID {client_uuid}: {assoc_resp.text}")
        except Exception as e:
            logger.error(f"Error assigning client scope {scope_name}: {e}")

def configure_user_service_client_solavie(keycloak_url, admin_token, realm_name):
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    base_url = keycloak_url.rstrip('/')

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

    sa_url = f"{base_url}/admin/realms/{realm_name}/clients/{user_svc_client_id}/service-account-user"
    try:
        sa_resp = requests.get(sa_url, headers=headers, timeout=10)
        sa_resp.raise_for_status()
        sa_user_id = sa_resp.json()["id"]
        logger.info(f"[user-service-client] Service account user ID: {sa_user_id}")
    except Exception as e:
        logger.error(f"[user-service-client] Failed to get service account user: {e}")
        return

    role_url = f"{base_url}/admin/realms/{realm_name}/clients/{realm_mgmt_client_id}/roles/manage-users"
    try:
        role_resp = requests.get(role_url, headers=headers, timeout=10)
        role_resp.raise_for_status()
        manage_users_role = role_resp.json()
        logger.info(f"[user-service-client] Found 'manage-users' role: {manage_users_role['id']}")
    except Exception as e:
        logger.error(f"[user-service-client] Failed to get 'manage-users' role from realm-management: {e}")
        return

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
    parser = argparse.ArgumentParser(description="Provision a new Keycloak Organization in shared realm 'solavie'.")
    parser.add_argument("--keycloak-url", default=os.getenv("KEYCLOAK_URL", "http://localhost:8081"), help="Keycloak server URL")
    parser.add_argument("--admin-username", default=os.getenv("KC_ADMIN", "admin"), help="Master admin username")
    parser.add_argument("--admin-password", default=os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass"), help="Master admin password")
    parser.add_argument("--template-path", default=os.path.join(os.path.dirname(__file__), "../templates/solavie-realm-template.json"), help="Path to shared realm config template")
    parser.add_argument("--tenant-id", required=True, help="Unique Tenant identifier (used as org alias, e.g. tenant-a-uuid)")
    parser.add_argument("--tenant-name", required=True, help="Display name of the tenant (used as org name)")
    parser.add_argument("--admin-email", required=True, help="Tenant admin email address")
    parser.add_argument("--admin-password-user", default="SolavieSecurePass123!", help="Tenant admin user password")
    parser.add_argument("--api-gateway-secret", help="Secret key for api-gateway confidential client (auto-generated if empty)")
    parser.add_argument("--user-service-secret", help="Secret key for user-service-client (auto-generated if empty)")
    parser.add_argument("--force", action="store_true", help="Recreate organization if it already exists")
    
    args = parser.parse_args()
    
    tenant_id = args.tenant_id.lower().strip()
    api_gateway_secret = args.api_gateway_secret or generate_secret()
    user_service_secret = args.user_service_secret or generate_secret()
    
    try:
        # Wait for Keycloak
        wait_for_keycloak(args.keycloak_url)
        
        logger.info(f"Starting organization provisioning process for tenant: {tenant_id} ({args.tenant_name})")
        admin_token = get_admin_token(args.keycloak_url, args.admin_username, args.admin_password)
        
        # 1. Ensure shared realm 'solavie' exists
        realm_name = "solavie"
        if not check_realm_exists(args.keycloak_url, admin_token, realm_name):
            logger.info(f"Shared realm '{realm_name}' does not exist. Creating from template...")
            create_shared_realm(args.keycloak_url, admin_token, args.template_path, api_gateway_secret, user_service_secret)
            # Configure custom scopes and user service client roles
            create_custom_client_scopes_solavie(args.keycloak_url, admin_token, realm_name)
            configure_user_service_client_solavie(args.keycloak_url, admin_token, realm_name)
        else:
            logger.info(f"Shared realm '{realm_name}' already exists.")
            
        # 2. Check if organization already exists
        org_id = get_organization_id(args.keycloak_url, admin_token, realm_name, tenant_id)
        if org_id:
            if args.force:
                logger.info(f"Organization '{tenant_id}' already exists. Deleting it due to --force flag...")
                delete_url = f"{args.keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations/{org_id}"
                del_resp = requests.delete(delete_url, headers={"Authorization": f"Bearer {admin_token}"}, timeout=10)
                del_resp.raise_for_status()
                logger.info(f"Deleted organization '{tenant_id}'.")
                org_id = None
            else:
                logger.warning(f"Organization '{tenant_id}' already exists. Skipping creation.")
                sys.exit(0)
                
        # 3. Create Organization
        logger.info(f"Creating Organization for tenant '{tenant_id}'...")
        org_id = create_organization(args.keycloak_url, admin_token, realm_name, tenant_id, args.tenant_name, args.admin_email)
        if not org_id:
            raise ValueError(f"Failed to retrieve Organization ID for alias '{tenant_id}'")
            
        # 4. Create Org Admin User
        logger.info("Creating Org Admin user...")
        user_id = create_org_user(args.keycloak_url, admin_token, realm_name, tenant_id, args.admin_email, args.admin_password_user)
        
        # 5. Add User to Org
        logger.info("Linking user to Organization...")
        add_member_to_org(args.keycloak_url, admin_token, realm_name, org_id, user_id)
        
        # 6. Assign Realm Role 'Admin' to User
        logger.info("Assigning realm-level 'Admin' role to user...")
        assign_realm_role_to_user(args.keycloak_url, admin_token, realm_name, user_id, "admin")
        
        logger.info(f"Organization provisioning successfully completed for: {tenant_id}")
        
        output = {
            "status": "success",
            "tenant_id": tenant_id,
            "tenant_name": args.tenant_name,
            "organization_id": org_id,
            "discovery_url": f"{args.keycloak_url.rstrip('/')}/realms/{realm_name}/.well-known/openid-configuration",
            "clients": {
                "dashboard": {
                    "client_id": "dashboard",
                    "type": "public"
                },
                "api-gateway": {
                    "client_id": "api-gateway",
                    "type": "confidential"
                },
                "user-service-client": {
                    "client_id": "user-service-client",
                    "type": "confidential"
                }
            },
            "admin_user": {
                "username": f"admin-{tenant_id}",
                "email": args.admin_email,
                "role": "admin"
            }
        }
        
        print("\nPROVISION_OUTPUT_START")
        print(json.dumps(output, indent=2))
        print("PROVISION_OUTPUT_END\n")
        
    except Exception as e:
        logger.critical(f"Organization provisioning failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

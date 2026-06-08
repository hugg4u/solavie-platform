#!/usr/bin/env python3
import argparse
import json
import logging
import os
import sys
import requests

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "category": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger("solavie.auth.migration_script")

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

def create_organization(keycloak_url, admin_token, realm_name, tenant_id, company_name, domain):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    
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
    
    response = requests.post(url, headers=headers, json=org_payload, timeout=10)
    if response.status_code == 201:
        location = response.headers.get("Location")
        if location:
            return location.split("/")[-1]
        return get_organization_id(keycloak_url, admin_token, realm_name, tenant_id)
    else:
        logger.error(f"Failed to create Organization. Status: {response.status_code}, Body: {response.text}")
        response.raise_for_status()



def get_users_from_realm(keycloak_url, admin_token, realm_name):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()

def get_user_realm_roles(keycloak_url, admin_token, realm_name, user_id):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users/{user_id}/role-mappings/realm"
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json()

def check_user_exists_in_realm(keycloak_url, admin_token, realm_name, username):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }
    response = requests.get(url, headers=headers, params={"username": username}, timeout=10)
    if response.status_code == 200:
        users = response.json()
        if users:
            return users[0]["id"]
    return None

def create_user_in_realm(keycloak_url, admin_token, realm_name, user_payload):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/users"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    response = requests.post(url, headers=headers, json=user_payload, timeout=10)
    if response.status_code == 201:
        location = response.headers.get("Location")
        if location:
            return location.split("/")[-1]
        # Fallback
        return check_user_exists_in_realm(keycloak_url, admin_token, realm_name, user_payload["username"])
    elif response.status_code == 409:
        logger.info(f"User '{user_payload['username']}' already exists in realm '{realm_name}'")
        return check_user_exists_in_realm(keycloak_url, admin_token, realm_name, user_payload["username"])
    else:
        logger.error(f"Failed to create user in realm '{realm_name}': {response.text}")
        response.raise_for_status()

def add_member_to_org(keycloak_url, admin_token, realm_name, org_id, user_id):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}/organizations/{org_id}/members"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    resp = requests.post(url, headers=headers, json=user_id, timeout=10)
    if resp.status_code not in [204, 201, 200]:
        logger.warning(f"Failed to add user '{user_id}' to organization member: {resp.text}")

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

def migrate_realm(keycloak_url, admin_token, old_realm_name, new_realm_name="solavie"):
    logger.info(f"Starting migration from realm '{old_realm_name}' to organization in realm '{new_realm_name}'")
    
    tenant_id = old_realm_name.lower().strip()
    company_name = f"Company for {tenant_id.capitalize()}"
    
    # Fetch users from old realm first to resolve domain
    logger.info(f"Fetching users from old realm '{old_realm_name}'...")
    old_users = get_users_from_realm(keycloak_url, admin_token, old_realm_name)
    logger.info(f"Found {len(old_users)} users to migrate.")
    
    # Resolve domain from the first valid email
    domain = f"{tenant_id}.com"
    for user in old_users:
        email = user.get("email")
        if email and "@" in email:
            parts = email.split("@")
            if len(parts) == 2:
                domain = parts[1]
                break

    # 1. Ensure Organization exists in solavie
    org_id = get_organization_id(keycloak_url, admin_token, new_realm_name, tenant_id)
    if not org_id:
        logger.info(f"Creating Organization '{company_name}' (alias: {tenant_id}) in realm '{new_realm_name}' with domain '{domain}'...")
        org_id = create_organization(keycloak_url, admin_token, new_realm_name, tenant_id, company_name, domain)
    else:
        logger.info(f"Organization for '{tenant_id}' already exists (ID: {org_id})")
        

    
    migrated_count = 0
    for user in old_users:
        username = user["username"]
        # Skip service account users
        if username.startswith("service-account-"):
            logger.info(f"Skipping service account user: {username}")
            continue
            
        logger.info(f"Migrating user: {username}")
        
        # 4. Construct user payload in new realm
        # We enforce email-based unique usernames or append suffix if necessary
        # However, we can keep the username, but prefix with admin- if it is the old 'admin' user
        # In multi-realm, every tenant has 'admin'. In single realm, they must be unique, e.g. admin-{tenant_id}
        new_username = username
        if username == "admin":
            new_username = f"admin-{tenant_id}"
            
        user_payload = {
            "username": new_username,
            "email": user.get("email"),
            "firstName": user.get("firstName", "Tenant"),
            "lastName": user.get("lastName", "User"),
            "enabled": user.get("enabled", True),
            "emailVerified": user.get("emailVerified", True),
            # Force password update after migration
            "requiredActions": ["UPDATE_PASSWORD"],
            "attributes": {
                "migrated_from": [old_realm_name],
                "original_id": [user["id"]]
            }
        }
        
        # 5. Create user in solavie realm
        new_user_id = create_user_in_realm(keycloak_url, admin_token, new_realm_name, user_payload)
        logger.info(f"User '{new_username}' exists/created in '{new_realm_name}' (ID: {new_user_id})")
        
        # 6. Add user to Organization
        add_member_to_org(keycloak_url, admin_token, new_realm_name, org_id, new_user_id)
        
        # 7. Map roles
        old_roles = get_user_realm_roles(keycloak_url, admin_token, old_realm_name, user["id"])
        for role in old_roles:
            role_name = role["name"].lower()
            if role_name in ["admin", "manager", "agent", "viewer"]:
                assign_realm_role_to_user(keycloak_url, admin_token, new_realm_name, new_user_id, role_name)
                
        migrated_count += 1
        
    logger.info(f"Migration completed. Successfully migrated {migrated_count} users to organization.")

def main():
    parser = argparse.ArgumentParser(description="Migrate users from an old realm to Keycloak Organizations in shared realm.")
    parser.add_argument("--keycloak-url", default=os.getenv("KEYCLOAK_URL", "http://localhost:8081"), help="Keycloak server URL")
    parser.add_argument("--admin-username", default=os.getenv("KC_ADMIN", "admin"), help="Master admin username")
    parser.add_argument("--admin-password", default=os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass"), help="Master admin password")
    parser.add_argument("--old-realm", required=True, help="Realm to migrate users from (e.g. tenant-test-uuid)")
    parser.add_argument("--new-realm", default="solavie", help="Target shared realm (default: solavie)")
    
    args = parser.parse_args()
    
    try:
        admin_token = get_admin_token(args.keycloak_url, args.admin_username, args.admin_password)
        migrate_realm(args.keycloak_url, admin_token, args.old_realm, args.new_realm)
    except Exception as e:
        logger.critical(f"Migration script failed: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

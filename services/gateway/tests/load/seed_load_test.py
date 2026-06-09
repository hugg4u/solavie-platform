#!/usr/bin/env python3
import os
import sys
import json
import time
import requests
import redis

# Load variables
REDIS_HOST = os.getenv("REDIS_HOST", "redis-master-1")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://solavie-keycloak:8080")
KC_ADMIN = os.getenv("KC_ADMIN", "admin")
KC_ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass")

def main():
    print(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}...")
    try:
        from redis.cluster import RedisCluster
        r = RedisCluster(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        r.ping()
        print("Connected to Redis Cluster successfully.")
        is_cluster = True
    except Exception as e:
        print(f"RedisCluster failed: {e}. Falling back to standalone Redis client.")
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            print("Connected to Standalone Redis successfully.")
            is_cluster = False
        except Exception as conn_err:
            print(f"Failed to connect to Redis: {conn_err}")
            sys.exit(1)

    print("Authenticating with Keycloak admin-cli...")
    token_url = f"{KEYCLOAK_URL}/realms/master/protocol/openid-connect/token"
    payload = {
        "client_id": "admin-cli",
        "username": KC_ADMIN,
        "password": KC_ADMIN_PASSWORD,
        "grant_type": "password"
    }
    try:
        resp = requests.post(token_url, data=payload, timeout=10)
        resp.raise_for_status()
        admin_token = resp.json()["access_token"]
    except Exception as e:
        print(f"Failed to authenticate with Keycloak: {e}")
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    # 1. Optimizing password policy & disabling brute force protection to speed up concurrent logins during stress testing
    print("Optimizing Keycloak realm security settings for stress testing (hashIterations=1, bruteForceProtected=False)...")
    try:
        realm_url = f"{KEYCLOAK_URL}/admin/realms/solavie"
        policy_payload = {
            "passwordPolicy": "hashIterations(1)",
            "bruteForceProtected": False
        }
        policy_resp = requests.put(realm_url, headers=headers, json=policy_payload, timeout=10)
        if policy_resp.status_code in [200, 204]:
            print("Successfully updated passwordPolicy and disabled bruteForceProtected.")
        else:
            print(f"Warning: Failed to update realm settings: {policy_resp.status_code} - {policy_resp.text}")
    except Exception as e:
        print(f"Warning: Failed to update realm settings due to exception: {e}")

    # 2. Create loadtest-user in solavie realm if not exists
    users_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users"
    print("Checking if loadtest-user exists...")
    try:
        resp = requests.get(users_url, headers=headers, params={"username": "loadtest-user"}, timeout=10)
        resp.raise_for_status()
        users = resp.json()
        if not users:
            print("Creating loadtest-user...")
            user_payload = {
                "username": "loadtest-user",
                "email": "loadtest@solavie-test.com",
                "firstName": "Load",
                "lastName": "Test",
                "enabled": True,
                "emailVerified": True,
                "credentials": [{"type": "password", "value": "LoadtestPassword123!", "temporary": False}]
            }
            create_resp = requests.post(users_url, headers=headers, json=user_payload, timeout=10)
            create_resp.raise_for_status()
            
            # Fetch user ID again
            resp = requests.get(users_url, headers=headers, params={"username": "loadtest-user"}, timeout=10)
            user_id = resp.json()[0]["id"]
        else:
            user_id = users[0]["id"]
            print(f"loadtest-user already exists with ID: {user_id}")
    except Exception as e:
        print(f"Failed to create/fetch loadtest-user: {e}")
        sys.exit(1)

    # 3. Ensure Manager role exists
    roles_url = f"{KEYCLOAK_URL}/admin/realms/solavie/roles"
    try:
        resp = requests.get(roles_url, headers=headers, timeout=10)
        resp.raise_for_status()
        roles = resp.json()
        role_exists = any(r["name"] == "Manager" or r["name"] == "manager" for r in roles)
        if not role_exists:
            print("Creating Manager role...")
            requests.post(roles_url, headers=headers, json={"name": "Manager"}, timeout=10)
        
        # Get role representation
        role_rep_resp = requests.get(f"{KEYCLOAK_URL}/admin/realms/solavie/roles/Manager", headers=headers, timeout=10)
        if role_rep_resp.status_code != 200:
            role_rep_resp = requests.get(f"{KEYCLOAK_URL}/admin/realms/solavie/roles/manager", headers=headers, timeout=10)
        role_rep = role_rep_resp.json()
        
        # Assign Manager role to loadtest-user
        mapping_url = f"{KEYCLOAK_URL}/admin/realms/solavie/users/{user_id}/role-mappings/realm"
        assign_resp = requests.post(mapping_url, headers=headers, json=[role_rep], timeout=10)
        if assign_resp.status_code in [204, 200, 201]:
            print("Assigned Manager role to loadtest-user successfully.")
        else:
            print(f"Warning: role mapping status code: {assign_resp.status_code}")
    except Exception as e:
        print(f"Failed to configure Manager role: {e}")
        sys.exit(1)

    # 3.5. Clear brute force status for loadtest-user to unlock it
    print("Unlocking loadtest-user from brute-force protection...")
    try:
        unlock_url = f"{KEYCLOAK_URL}/admin/realms/solavie/attack-detection/brute-force/users/{user_id}"
        unlock_resp = requests.delete(unlock_url, headers=headers, timeout=10)
        if unlock_resp.status_code in [200, 204]:
            print("Successfully unlocked loadtest-user.")
        else:
            print(f"Warning: Failed to unlock user: {unlock_resp.status_code} - {unlock_resp.text}")
    except Exception as e:
        print(f"Warning: Failed to unlock user due to exception: {e}")

    # 4. Seed Redis with 10,000 tenants using Pipeline
    total_tenants = 10000
    print(f"Seeding {total_tenants} tenants in Redis using Pipeline...")
    try:
        pipe = r.pipeline()
        for i in range(total_tenants):
            tenant_id = f"tenant-loadtest-{i}"
            
            # Seed Tenant config
            config_key = f"tenant:{tenant_id}:config:security_comments_notif"
            config_data = {
                "gateway_rate_limit_minute": 100000,
                "gateway_rate_limit_hour": 1000000,
                "allowed_cors_origins": ["*"]
            }
            pipe.set(config_key, json.dumps(config_data))
            
            # Seed role permissions (using Capitalized role 'Manager' to match Keycloak)
            perm_key = f"tenant:{tenant_id}:role:Manager:permissions"
            perm_data = ["ai-core:completions", "ai-core:embeddings"]
            pipe.set(perm_key, json.dumps(perm_data))
            
            # Execute batches of 1,000 to prevent buffer overload
            if (i + 1) % 1000 == 0:
                pipe.execute()
                print(f"  Seeded {i + 1} tenants...")
                pipe = r.pipeline()
                
        # Execute any remaining requests
        pipe.execute()
        print(f"Successfully seeded {total_tenants} tenants in Redis.")
    except Exception as e:
        print(f"Failed to seed Redis: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

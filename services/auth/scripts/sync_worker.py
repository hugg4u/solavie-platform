#!/usr/bin/env python3
import json
import logging
import os
import sys
import time
import redis
import requests

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "category": "%(name)s", "message": "%(message)s"}'
)
logger = logging.getLogger("solavie.auth.sync_worker")

# Environment Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")
KC_ADMIN = os.getenv("KC_ADMIN", "admin")
KC_ADMIN_PASSWORD = os.getenv("KC_ADMIN_PASSWORD", "admin_secret_pass")

def wait_for_keycloak(keycloak_url, timeout=120):
    url = f"{keycloak_url.rstrip('/')}/health/ready"
    start_time = time.time()
    logger.info(f"Waiting for Keycloak to become ready at: {url}")
    while True:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                logger.info("Keycloak is ready for synchronization!")
                return True
        except Exception:
            pass
        if time.time() - start_time > timeout:
            raise TimeoutError("Timed out waiting for Keycloak to start up and become ready.")
        time.sleep(3)

def get_admin_token(keycloak_url, admin_username, admin_password):
    url = f"{keycloak_url.rstrip('/')}/realms/master/protocol/openid-connect/token"
    data = {
        "client_id": "admin-cli",
        "username": admin_username,
        "password": admin_password,
        "grant_type": "password"
    }
    response = requests.post(url, data=data, timeout=10)
    response.raise_for_status()
    return response.json()["access_token"]

def get_realms(keycloak_url, admin_token):
    url = f"{keycloak_url.rstrip('/')}/admin/realms"
    headers = {
        "Authorization": f"Bearer {admin_token}"
    }
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return [realm["realm"] for realm in response.json() if realm["realm"] != "master"]

def update_realm_security(keycloak_url, admin_token, realm_name, min_length, max_attempts):
    url = f"{keycloak_url.rstrip('/')}/admin/realms/{realm_name}"
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "passwordPolicy": f"length({min_length}) and upperCase(1) and digits(1) and specialChars(1)",
        "bruteForceProtected": True,
        "failureFactor": max_attempts
    }
    logger.info(f"Updating realm '{realm_name}' with passwordPolicy length({min_length}) and failureFactor({max_attempts})")
    response = requests.put(url, headers=headers, json=payload, timeout=10)
    if response.status_code == 204:
        logger.info(f"Successfully updated realm '{realm_name}' security policy.")
    else:
        logger.error(f"Failed to update realm '{realm_name}' security policy. Status: {response.status_code}, Body: {response.text}")

def sync_realm_security(r, tenant_id):
    keys = [
        f"tenant:{tenant_id}:config:security_comments_notif",
        f"{tenant_id}:config:security_comments_notif"
    ]
    config_data = None
    for key in keys:
        val = r.get(key)
        if val:
            try:
                config_data = json.loads(val)
                logger.info(f"Found config in Redis for tenant: {tenant_id} under key {key}")
                break
            except Exception as e:
                logger.error(f"Failed to parse JSON config for key {key}: {str(e)}")
                
    if not config_data:
        logger.warning(f"No valid config found in Redis for tenant: {tenant_id}. Using default policies.")
        min_length = 8
        max_attempts = 5
    else:
        min_length = config_data.get("auth_password_min_length", 8)
        max_attempts = config_data.get("auth_max_login_attempts", 5)
        
    try:
        admin_token = get_admin_token(KEYCLOAK_URL, KC_ADMIN, KC_ADMIN_PASSWORD)
        update_realm_security(KEYCLOAK_URL, admin_token, tenant_id, min_length, max_attempts)
    except Exception as e:
        logger.error(f"Failed to update Keycloak settings for tenant {tenant_id}: {str(e)}")

def initial_sync(r):
    try:
        admin_token = get_admin_token(KEYCLOAK_URL, KC_ADMIN, KC_ADMIN_PASSWORD)
        realms = get_realms(KEYCLOAK_URL, admin_token)
        logger.info(f"Found {len(realms)} active tenant realms: {realms}. Starting initial sync...")
        for realm in realms:
            sync_realm_security(r, realm)
    except Exception as e:
        logger.error(f"Initial sync failed: {str(e)}")

def main():
    logger.info("Starting Auth Security Sync Worker...")
    try:
        # Wait for Keycloak
        wait_for_keycloak(KEYCLOAK_URL)
        
        # Connect to Redis
        r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        
        # Perform initial sync for existing realms
        initial_sync(r)
        
        # Setup Redis Stream Consumer Group for config.updates.stream
        stream_name = "config.updates.stream"
        group_name = "auth-sync-group"
        consumer_name = "worker-1"
        
        try:
            r.xgroup_create(stream_name, group_name, id="0", mkstream=True)
            logger.info(f"Created Redis Stream consumer group '{group_name}' for stream '{stream_name}'")
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group '{group_name}' already exists.")
            else:
                logger.error(f"Failed to create consumer group: {str(e)}")

        # Setup Pub/Sub listener
        pubsub = r.pubsub()
        pubsub.subscribe(["config.updates", "token.revoked"])
        logger.info("Subscribed to Redis channels 'config.updates' and 'token.revoked'.")
        
        while True:
            # 1. Check Pub/Sub messages (non-blocking check with timeout)
            try:
                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                if message and message['type'] == 'message':
                    channel = message['channel']
                    payload = message['data']
                    logger.info(f"Received pub/sub message on channel '{channel}': {payload}")
                    
                    data = json.loads(payload)
                    if channel == "config.updates":
                        category = data.get("category")
                        tenant_id = data.get("tenant_id")
                        if category == "security_comments_notif" and tenant_id:
                            logger.info(f"Triggering security sync for tenant: {tenant_id}")
                            sync_realm_security(r, tenant_id)
                    elif channel == "token.revoked":
                        jti = data.get("jti")
                        exp = data.get("exp")
                        if jti and exp:
                            # Calculate TTL: exp is epoch timestamp
                            ttl = int(exp - time.time())
                            if ttl > 0:
                                r.setex(f"blacklist:jti:{jti}", ttl, "revoked")
                                logger.info(f"Successfully blacklisted token JTI '{jti}' for {ttl} seconds.")
            except Exception as e:
                logger.error(f"Error processing pub/sub message: {str(e)}")

            # 2. Check Redis Stream config.updates.stream messages
            try:
                streams = r.xreadgroup(group_name, consumer_name, {stream_name: ">"}, count=1, block=100)
                if streams:
                    for stream, messages in streams:
                        for message_id, msg_data in messages:
                            logger.info(f"Received stream message [{message_id}]: {msg_data}")
                            payload_str = msg_data.get("data")
                            if payload_str:
                                data = json.loads(payload_str)
                                category = data.get("category")
                                tenant_id = data.get("tenant_id")
                                if category == "security_comments_notif" and tenant_id:
                                    logger.info(f"Stream Sync: Triggering security sync for tenant: {tenant_id}")
                                    sync_realm_security(r, tenant_id)
                            # Acknowledge the message has been processed successfully
                            r.xack(stream_name, group_name, message_id)
                            logger.info(f"ACKed stream message [{message_id}]")
            except Exception as e:
                logger.error(f"Error processing Redis Stream message: {str(e)}")
                
            time.sleep(0.1)
            
    except Exception as e:
        logger.critical(f"Sync Worker terminated due to error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()

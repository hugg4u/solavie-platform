#!/usr/bin/env python3
import json
import logging
import os
import sys
import time
import hmac
import hashlib
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

# AC 4.8: User Service Webhook for event forwarding
USER_SERVICE_WEBHOOK_URL = os.getenv("USER_SERVICE_WEBHOOK_URL", "http://user-service:3008/api/v1/users/events")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")


def wait_for_keycloak(keycloak_url, timeout=120):
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

def forward_user_event_to_service(event_payload: dict):
    """
    AC 4.8: Forward Keycloak user events sang User Service webhook.
    Ký HMAC-SHA256 dựa trên WEBHOOK_SECRET để User Service có thể xác thực chữ ký.
    Map từ event type của Keycloak sang chuẩn event của User Service.
    """
    # Map Keycloak event types -> User Service event schema
    kc_event_map = {
        "VERIFY_EMAIL": "user.verified",
        "REGISTER": "user.verified",
        "UPDATE_EMAIL": "user.email_updated",
        "DISABLE_USER": "user.disabled",
        "DELETE_USER": "user.deleted",
    }

    raw_event = event_payload.get("event") or event_payload.get("type", "")
    mapped_event = kc_event_map.get(raw_event, raw_event)

    webhook_payload = {
        "event": mapped_event,
        "userId": event_payload.get("user_id") or event_payload.get("userId"),
        "realm": event_payload.get("realm") or event_payload.get("realmId"),
        "email": event_payload.get("email"),
    }

    payload_str = json.dumps(webhook_payload, separators=(",", ":"))

    # Sign payload with HMAC-SHA256
    signature = ""
    if WEBHOOK_SECRET:
        mac = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            payload_str.encode("utf-8"),
            hashlib.sha256
        )
        signature = mac.hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature,
    }

    try:
        resp = requests.post(USER_SERVICE_WEBHOOK_URL, data=payload_str, headers=headers, timeout=5)
        if resp.status_code in [200, 201, 204]:
            logger.info(f"[ac4.8] Forwarded user event '{mapped_event}' for userId={webhook_payload['userId']} to User Service. Status: {resp.status_code}")
        else:
            logger.error(f"[ac4.8] Failed to forward user event '{mapped_event}' to User Service. Status: {resp.status_code}, Body: {resp.text}")
    except Exception as e:
        logger.error(f"[ac4.8] Error forwarding user event to User Service: {e}")


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
        pubsub.subscribe(["config.updates", "token.revoked", "auth.user.events"])
        logger.info("Subscribed to Redis channels: 'config.updates', 'token.revoked', 'auth.user.events'.")
        
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
                    elif channel == "auth.user.events":
                        # AC 4.8: Forward Keycloak user lifecycle events to User Service
                        logger.info(f"[ac4.8] Received user event from Keycloak: {data}")
                        forward_user_event_to_service(data)
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

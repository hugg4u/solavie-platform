"""
generate_kong_config.py
Generates a declarative configuration file for Kong (kong.yml) dynamically,
fetching the necessary public keys from Keycloak for JWT signature validation.
"""
import os
import sys
import logging
from typing import Dict, Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import yaml

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

# Environment Configuration
KEYCLOAK_URL: str = os.environ.get("KEYCLOAK_URL", "http://keycloak:8080")
TENANT_ID: str = os.environ.get("TENANT_ID", "tenant-test-uuid")
# Issuer URL that the token will contain (must exactly match Keycloak's generated token 'iss')
KONG_ISSUER_URL: str = os.environ.get(
    "KONG_ISSUER_URL", "http://localhost:8081/realms/solavie"
)
KONG_CONFIG_PATH: str = os.environ.get("KONG_CONFIG_PATH", "/etc/kong/kong.yml")

# Redis Configuration (Dynamic via env)
REDIS_HOST: str = os.environ.get("REDIS_HOST", "redis-master-1")
REDIS_PORT: int = int(os.environ.get("REDIS_PORT", 6379))

# Downstream Webhook/Connector Configuration (Dynamic via env)
CHANNEL_CONNECTOR_URL: str = os.environ.get("CHANNEL_CONNECTOR_URL", "http://127.0.0.1:3001")

# Additional Decoupled Configuration
MOCK_API_INTERNAL_URL: str = os.environ.get("MOCK_API_INTERNAL_URL", "http://127.0.0.1:80")
GATEWAY_FALLBACK_TARGET: str = os.environ.get("GATEWAY_FALLBACK_TARGET", "127.0.0.1:8000")
KEYCLOAK_BACKUP_ISSUER_URL: str = os.environ.get("KEYCLOAK_BACKUP_ISSUER_URL", "http://localhost:8080/realms/solavie")


class KeycloakConnectionError(Exception):
    """Exception raised when connection to Keycloak fails after retries."""
    pass


def get_requests_session() -> requests.Session:
    """Creates a requests Session with retry logic."""
    session = requests.Session()
    retry_strategy = Retry(
        total=15,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def get_public_key(session: requests.Session) -> str:
    """Fetches the realm's public key from Keycloak."""
    url = f"{KEYCLOAK_URL}/realms/solavie/"
    logger.info(f"Fetching public key from {url}")
    
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if "public_key" not in data:
            logger.error("Response JSON does not contain 'public_key'.")
            raise KeycloakConnectionError("Missing public_key in response")
            
        return str(data["public_key"])
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch public key from Keycloak: {e}")
        raise KeycloakConnectionError(f"Connection failed: {e}") from e


def format_public_key(key_string: str) -> str:
    """Formats a base64 string into a valid PEM format public key."""
    lines = ["-----BEGIN PUBLIC KEY-----"]
    lines.extend(key_string[i:i + 64] for i in range(0, len(key_string), 64))
    lines.append("-----END PUBLIC KEY-----")
    return "\n".join(lines) + "\n"


def build_upstream_config(name: str) -> Dict[str, Any]:
    """Helper to build standard upstream configuration block with healthchecks."""
    return {
        "name": name,
        "algorithm": "round-robin",
        "slots": 10000,
        "healthchecks": {
            "active": {
                "type": "http",
                "http_path": "/health",
                "timeout": 1,
                "concurrency": 10,
                "healthy": {
                    "interval": 5,
                    "successes": 2
                },
                "unhealthy": {
                    "interval": 2,
                    "http_failures": 2,
                    "timeouts": 2
                }
            }
        },
        "targets": [
            {
                "target": GATEWAY_FALLBACK_TARGET,
                "weight": 0
            }
        ]
    }


def build_kong_config(public_key_pem: str) -> Dict[str, Any]:
    """Builds the declarative Kong configuration dictionary."""
    jwt_plugin = {
        "name": "jwt",
        "config": {
            "key_claim_name": "iss",
            "claims_to_verify": ["exp"]
        }
    }
    
    request_termination_plugin = {
        "name": "request-termination",
        "config": {
            "status_code": 200,
            "message": "Webhook health check mock OK"
        }
    }
    
    services = [
        {
            "name": "auth-service",
            "url": KEYCLOAK_URL,
            "routes": [
                {
                    "name": "auth-route",
                    "paths": ["/api/v1/auth"],
                    "strip_path": True,
                    "plugins": [jwt_plugin]
                }
            ]
        },
        {
            "name": "ai-core",
            "url": "http://ai-core-upstream",
            "routes": [
                {
                    "name": "ai-jobs-api",
                    "paths": ["/api/v1/completions/jobs"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:media-processor"]
                },
                {
                    "name": "ai-api",
                    "paths": [
                        "/api/v1/completions",
                        "/api/v1/embeddings",
                        "/api/v1/models",
                        "/api/v1/configs",
                        "/api/v1/analytics",
                        "/api/v1/prompts"
                    ],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:ai-core"]
                }
            ]
        },
        {
            "name": "tenant-config",
            "url": "http://tenant-config-upstream",
            "routes": [
                {
                    "name": "tenant-config-api",
                    "paths": ["/api/v1/config"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:tenant-config"]
                }
            ]
        },
        {
            "name": "knowledge-base",
            "url": "http://knowledge-base-upstream",
            "routes": [
                {
                    "name": "kb-api",
                    "paths": ["/api/v1/documents", "/api/v1/search"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:knowledge-base"]
                }
            ]
        },
        {
            "name": "chatbot",
            "url": "http://chatbot-upstream",
            "routes": [
                {
                    "name": "chatbot-api",
                    "paths": ["/api/v1/chatbot"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:chatbot"]
                }
            ]
        },
        {
            "name": "user-service",
            "url": "http://user-service-upstream",
            "routes": [
                {
                    "name": "user-api",
                    "paths": ["/api/v1/users"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:auth"]
                },
                {
                    "name": "user-permissions-manifest",
                    "paths": ["/api/v1/permissions/manifest"],
                    "strip_path": False
                }
            ]
        },
        {
            "name": "channel-connector-webhooks",
            "url": CHANNEL_CONNECTOR_URL,
            "routes": [
                {
                    "name": "webhooks",
                    "paths": ["/webhooks"],
                    "strip_path": False,
                    "plugins": [request_termination_plugin]
                }
            ]
        },
        {
            "name": "mock-api",
            "url": MOCK_API_INTERNAL_URL,
            "routes": [
                {
                    "name": "mock-completions",
                    "paths": ["/api/v1/mock-completions"],
                    "strip_path": False,
                    "plugins": [
                        jwt_plugin,
                        {
                            "name": "request-termination",
                            "config": {
                                "status_code": 200,
                                "body": "{\"message\": \"mock success\"}",
                                "content_type": "application/json"
                            }
                        }
                    ],
                    "tags": ["scope:ai-core"]
                }
            ]
        },
        # === REST Services dynamically managed by Discovery ===
        {
            "name": "campaign",
            "url": "http://campaign-upstream",
            "routes": [
                {
                    "name": "campaign-api",
                    "paths": ["/api/v1/campaigns"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:campaign"]
                }
            ]
        },
        {
            "name": "crm",
            "url": "http://crm-upstream",
            "routes": [
                {
                    "name": "crm-api",
                    "paths": ["/api/v1/contacts", "/api/v1/segments", "/api/v1/deals", "/api/v1/tickets"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:crm"]
                }
            ]
        },
        {
            "name": "analytics",
            "url": "http://analytics-upstream",
            "routes": [
                {
                    "name": "analytics-api",
                    "paths": ["/api/v1/metrics", "/api/v1/reports", "/api/v1/insights"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:analytics"]
                }
            ]
        },
        {
            "name": "comment-manager",
            "url": "http://comment-manager-upstream",
            "routes": [
                {
                    "name": "comment-api",
                    "paths": ["/api/v1/comments"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:comment-manager"]
                }
            ]
        },
        {
            "name": "dms",
            "url": "http://dms-upstream",
            "routes": [
                {
                    "name": "dms-files-api",
                    "paths": ["/api/v1/files", "/api/v1/folders", "/api/v1/upload", "/api/v1/trash", "/api/v1/quota"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:dms"]
                }
            ]
        },
        {
            "name": "link-shortener",
            "url": "http://link-shortener-upstream",
            "routes": [
                {
                    "name": "link-shortener-api",
                    "paths": ["/api/v1/links"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:link-shortener"]
                },
                {
                    "name": "link-shortener-redirect",
                    "paths": ["/r"],
                    "strip_path": True
                }
            ]
        },
        {
            "name": "media-processor",
            "url": "http://media-processor-upstream",
            "routes": [
                {
                    "name": "media-processor-api",
                    "paths": ["/api/v1/media/jobs"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:media-processor"]
                }
            ]
        },
        {
            "name": "notification",
            "url": "http://notification-upstream",
            "routes": [
                {
                    "name": "notification-api",
                    "paths": ["/api/v1/notifications", "/api/v1/preferences"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:notification"]
                }
            ]
        },
        {
            "name": "channel-connector",
            "url": "http://channel-connector-upstream",
            "routes": [
                {
                    "name": "channel-connector-api",
                    "paths": ["/api/v1/channels"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:channel-connector"]
                }
            ]
        },
        {
            "name": "scheduler",
            "url": "http://scheduler-upstream",
            "routes": [
                {
                    "name": "scheduler-api",
                    "paths": ["/api/v1/schedules", "/api/v1/automations"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:scheduler"]
                }
            ]
        },
        {
            "name": "messaging",
            "url": "http://messaging-upstream",
            "routes": [
                {
                    "name": "messaging-api",
                    "paths": ["/api/v1/conversations", "/api/v1/messages"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:messaging"]
                },
                {
                    "name": "messaging-ws",
                    "paths": ["/ws"],
                    "strip_path": False,
                    "protocols": ["ws", "wss"],
                    "tags": ["scope:messaging"]
                }
            ]
        },
        # === Dedicated MCP SSE Services (with 60s timeouts) ===
        {
            "name": "crm-mcp",
            "url": "http://crm-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "crm-mcp-route",
                    "paths": ["/api/v1/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:crm"]
                }
            ]
        },
        {
            "name": "knowledge-base-mcp",
            "url": "http://knowledge-base-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "kb-mcp-route",
                    "paths": ["/api/v1/kb/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:knowledge-base"]
                }
            ]
        },
        {
            "name": "messaging-mcp",
            "url": "http://messaging-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "messaging-mcp-route",
                    "paths": ["/api/v1/messaging/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:messaging"]
                }
            ]
        },
        {
            "name": "notification-mcp",
            "url": "http://notification-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "notification-mcp-route",
                    "paths": ["/api/v1/notification/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:notification"]
                }
            ]
        },
        {
            "name": "comment-manager-mcp",
            "url": "http://comment-manager-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "comment-manager-mcp-route",
                    "paths": ["/api/v1/comments/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:comment-manager"]
                }
            ]
        },
        {
            "name": "content-mcp",
            "url": "http://content-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "content-mcp-route",
                    "paths": ["/api/v1/content/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:content"]
                }
            ]
        },
        {
            "name": "scheduler-mcp",
            "url": "http://scheduler-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "scheduler-mcp-route",
                    "paths": ["/api/v1/scheduler/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:scheduler"]
                }
            ]
        },
        {
            "name": "analytics-mcp",
            "url": "http://analytics-upstream",
            "connect_timeout": 60000,
            "read_timeout": 60000,
            "write_timeout": 60000,
            "routes": [
                {
                    "name": "analytics-mcp-route",
                    "paths": ["/api/v1/analytics/mcp"],
                    "strip_path": False,
                    "plugins": [jwt_plugin],
                    "tags": ["scope:analytics"]
                }
            ]
        }
    ]
    
    upstream_names = [
        "ai-core-upstream", "user-service-upstream", "tenant-config-upstream",
        "chatbot-upstream", "knowledge-base-upstream", "campaign-upstream",
        "crm-upstream", "analytics-upstream", "comment-manager-upstream",
        "dms-upstream", "link-shortener-upstream", "media-processor-upstream",
        "notification-upstream", "channel-connector-upstream", "scheduler-upstream",
        "messaging-upstream"
    ]
    upstreams = [build_upstream_config(name) for name in upstream_names]
    
    return {
        "_format_version": "3.0",
        "_transform": True,
        "services": services,
        "upstreams": upstreams,
        "plugins": [
            {
                "name": "dynamic-policy",
                "config": {
                    "redis_host": REDIS_HOST,
                    "redis_port": REDIS_PORT,
                    "tenant_config_internal_url": os.environ.get("TENANT_CONFIG_INTERNAL_URL", "http://tenant-config:3006"),
                    "default_tenant_id": os.environ.get("DEFAULT_TENANT_ID", "tenant-test-uuid"),
                    "default_rate_limit_minute": int(os.environ.get("DEFAULT_RATE_LIMIT_MINUTE", 200)),
                    "default_rate_limit_hour": int(os.environ.get("DEFAULT_RATE_LIMIT_HOUR", 5000)),
                    "gateway_signing_secret": os.environ.get("GATEWAY_SIGNING_SECRET", "default-gateway-signing-secret-key-change-me-in-production")
                }
            },
            {
                "name": "prometheus",
                "config": {
                    "per_consumer": True,
                    "status_code_metrics": True,
                    "latency_metrics": True
                }
            }
        ],
        "consumers": [
            {
                "username": "keycloak_issuer"
            }
        ],
        "jwt_secrets": [
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": KONG_ISSUER_URL,
                "rsa_public_key": public_key_pem
            },
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": f"{KEYCLOAK_URL}/realms/solavie",
                "rsa_public_key": public_key_pem
            },
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": f"{KEYCLOAK_URL.replace('keycloak', 'solavie-keycloak')}/realms/solavie",
                "rsa_public_key": public_key_pem
            },
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": KEYCLOAK_BACKUP_ISSUER_URL,
                "rsa_public_key": public_key_pem
            }
        ]
    }


def generate_kong_yml(public_key_pem: str) -> None:
    """Writes the generated configuration to the target YAML file."""
    config = build_kong_config(public_key_pem)
    
    try:
        config_dir = os.path.dirname(KONG_CONFIG_PATH)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)
        
        with open(KONG_CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.dump(config, f, sort_keys=False)
            
        logger.info(f"Kong configuration generated successfully at '{KONG_CONFIG_PATH}'")
    except IOError as e:
        logger.error(f"Failed to write Kong config file: {e}")
        sys.exit(1)


def main() -> None:
    session = get_requests_session()
    try:
        pub_key_raw = get_public_key(session)
    except KeycloakConnectionError:
        sys.exit(1)
        
    pub_key_pem = format_public_key(pub_key_raw)
    generate_kong_yml(pub_key_pem)


if __name__ == "__main__":
    main()

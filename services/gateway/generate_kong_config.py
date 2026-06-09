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
    
    return {
        "_format_version": "3.0",
        "_transform": True,
        "services": [
            {
                "name": "auth-service",
                "url": "http://keycloak:8080",
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
                "url": "http://ai-core:8000",
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
                "url": "http://tenant-config:3006",
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
                "url": "http://knowledge-base:8004",
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
                "url": "http://chatbot:8001",
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
                "url": "http://user-service:3008",
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
                "url": "http://127.0.0.1:3001",
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
                "url": "http://127.0.0.1:80",
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
            }
        ],
        "plugins": [
            {
                "name": "dynamic-policy",
                "config": {
                    "redis_host": "redis-master-1",
                    "redis_port": 6379
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
                "key": "http://solavie-keycloak:8080/realms/solavie",
                "rsa_public_key": public_key_pem
            },
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": "http://keycloak:8080/realms/solavie",
                "rsa_public_key": public_key_pem
            },
            {
                "consumer": "keycloak_issuer",
                "algorithm": "RS256",
                "key": "http://localhost:8080/realms/solavie",
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

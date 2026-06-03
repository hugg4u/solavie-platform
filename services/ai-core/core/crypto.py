import base64
import hashlib
from cryptography.fernet import Fernet
from core.config import settings

def get_fernet_key() -> bytes:
    """Derive a 32-byte urlsafe base64-encoded key from the ENCRYPTION_SECRET_KEY settings."""
    secret = settings.ENCRYPTION_SECRET_KEY or "solavie_super_secret_master_key_change_me_in_production"
    hasher = hashlib.sha256(secret.encode('utf-8'))
    derived_bytes = hasher.digest()
    return base64.urlsafe_b64encode(derived_bytes)

def encrypt_key(key: str) -> str:
    """Encrypt a plain text key using Fernet (AES-256)."""
    if not key:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.encrypt(key.encode('utf-8')).decode('utf-8')

def decrypt_key(encrypted_key: str) -> str:
    """Decrypt an encrypted key using Fernet (AES-256)."""
    if not encrypted_key:
        return ""
    fernet = Fernet(get_fernet_key())
    return fernet.decrypt(encrypted_key.encode('utf-8')).decode('utf-8')

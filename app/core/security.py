"""Security utilities for token encryption and signature verification."""

import hmac
import hashlib
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet
from passlib.context import CryptContext
from jose import jwt


class TokenEncryption:
    """Thread-safe token encryption using Fernet."""

    def __init__(self, encryption_key: str):
        self.fernet = Fernet(encryption_key.encode())

    def encrypt(self, token: str) -> str:
        """Encrypt a token."""
        return self.fernet.encrypt(token.encode()).decode()

    def decrypt(self, encrypted_token: str) -> str:
        """Decrypt an encrypted token."""
        return self.fernet.decrypt(encrypted_token.encode()).decode()


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def verify_slack_signature(
    body: str,
    timestamp: str,
    signature: str,
    signing_secret: str,
    max_age_seconds: int = 300
) -> bool:
    """Verify Slack request signature using HMAC SHA256."""
    if not signature.startswith("v0="):
        return False

    try:
        request_time = int(timestamp)
    except ValueError:
        return False

    current_time = int(time.time())
    if abs(current_time - request_time) > max_age_seconds:
        return False

    sig_basestring = f"v0:{timestamp}:{body}"
    expected_signature = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    return hmac.compare_digest(expected_signature, signature)


def create_access_token(
    data: Dict[str, Any],
    secret_key: str,
    algorithm: str = "HS256",
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, secret_key, algorithm=algorithm)


# Global token encryption instance
_token_encryption: Optional[TokenEncryption] = None


def init_token_encryption(encryption_key: str) -> None:
    """Initialize the global token encryption instance."""
    global _token_encryption
    _token_encryption = TokenEncryption(encryption_key)


def encrypt_token(token: str) -> str:
    """Encrypt a token using the global encryption instance."""
    if _token_encryption is None:
        raise RuntimeError("Token encryption not initialized")
    return _token_encryption.encrypt(token)


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt an encrypted token using the global encryption instance."""
    if _token_encryption is None:
        raise RuntimeError("Token encryption not initialized")
    return _token_encryption.decrypt(encrypted_token)

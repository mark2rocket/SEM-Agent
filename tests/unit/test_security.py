"""Unit tests for security module."""

import pytest
from datetime import datetime, timedelta
import time

from app.core.security import (
    TokenEncryption,
    verify_slack_signature,
    create_access_token,
    hash_password,
    verify_password
)


class TestTokenEncryption:
    """Test token encryption/decryption."""

    def test_encryption_decryption(self):
        """Test that encryption and decryption work correctly."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()

        encryptor = TokenEncryption(key)
        original_token = "test_token_12345"

        encrypted = encryptor.encrypt(original_token)
        assert encrypted != original_token
        assert isinstance(encrypted, str)

        decrypted = encryptor.decrypt(encrypted)
        assert decrypted == original_token

    def test_encryption_with_different_tokens(self):
        """Test that different tokens produce different encrypted values."""
        from cryptography.fernet import Fernet
        key = Fernet.generate_key().decode()

        encryptor = TokenEncryption(key)
        token1 = "token_1"
        token2 = "token_2"

        encrypted1 = encryptor.encrypt(token1)
        encrypted2 = encryptor.encrypt(token2)

        assert encrypted1 != encrypted2
        assert encryptor.decrypt(encrypted1) == token1
        assert encryptor.decrypt(encrypted2) == token2


class TestPasswordHashing:
    """Test password hashing functions."""

    def test_password_hashing(self):
        """Test password hashing and verification."""
        password = "secure_password_123"

        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)

    def test_wrong_password_fails(self):
        """Test that wrong password fails verification."""
        password = "correct_password"
        wrong_password = "wrong_password"

        hashed = hash_password(password)
        assert not verify_password(wrong_password, hashed)

    def test_same_password_different_hashes(self):
        """Test that same password produces different hashes (salt)."""
        password = "test_password"

        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert verify_password(password, hash1)
        assert verify_password(password, hash2)


class TestSlackSignatureVerification:
    """Test Slack signature verification."""

    def test_valid_signature(self):
        """Test that valid signature passes verification."""
        body = '{"type":"url_verification","challenge":"test"}'
        timestamp = str(int(time.time()))
        signing_secret = "test_secret"

        # Generate valid signature
        import hmac
        import hashlib
        sig_basestring = f"v0:{timestamp}:{body}"
        signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        assert verify_slack_signature(body, timestamp, signature, signing_secret)

    def test_invalid_signature_fails(self):
        """Test that invalid signature fails verification."""
        body = '{"type":"test"}'
        timestamp = str(int(time.time()))
        signing_secret = "secret"
        wrong_signature = "v0=wrong_signature"

        assert not verify_slack_signature(body, timestamp, wrong_signature, signing_secret)

    def test_old_timestamp_fails(self):
        """Test that old timestamp fails verification (replay attack protection)."""
        body = '{"type":"test"}'
        old_timestamp = str(int(time.time()) - 400)  # 400 seconds ago
        signing_secret = "secret"

        import hmac
        import hashlib
        sig_basestring = f"v0:{old_timestamp}:{body}"
        signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        # Should fail due to timestamp being too old (>300 seconds)
        # Function returns False for invalid timestamps, does not raise exception
        result = verify_slack_signature(body, old_timestamp, signature, signing_secret)
        assert result is False


class TestJWTTokens:
    """Test JWT token creation and validation."""

    def test_create_access_token(self):
        """Test creating JWT access token."""
        data = {"sub": "user123", "role": "admin"}
        secret_key = "test_secret_key"

        token = create_access_token(data, secret_key)
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_with_expiration(self):
        """Test token with custom expiration."""
        data = {"sub": "user123"}
        secret_key = "test_secret_key"
        expires_delta = timedelta(hours=1)

        token = create_access_token(data, secret_key, expires_delta=expires_delta)
        assert isinstance(token, str)

        # Decode and verify expiration
        from jose import jwt
        decoded = jwt.decode(token, secret_key, algorithms=["HS256"])
        assert "exp" in decoded
        assert "sub" in decoded
        assert decoded["sub"] == "user123"

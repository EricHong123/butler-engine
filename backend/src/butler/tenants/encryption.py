"""
Per-tenant envelope encryption for sensitive PII fields.

Architecture:
  - Master key (32 bytes) encrypts per-tenant data keys
  - Per-tenant data keys encrypt individual fields
  - AES-256-GCM for authenticated encryption
  - Key rotation supported via versioned data keys
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from Crypto.Cipher import AES
from Crypto.Protocol.KDF import HKDF
from Crypto.Hash import SHA256


@dataclass
class DataKey:
    """A versioned data encryption key for one tenant."""
    key_id: str
    key_material: bytes  # 32 bytes for AES-256
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    is_active: bool = True


class TenantEncryption:
    """
    Per-tenant envelope encryption manager.

    Master key → encrypts per-tenant DataKeys → DataKeys encrypt PII fields.
    """

    GCM_NONCE_SIZE = 12
    GCM_TAG_SIZE = 16

    def __init__(self, master_key_hex: str | None = None):
        if master_key_hex:
            self._master_key = bytes.fromhex(master_key_hex)
        else:
            # Try KMS first, then env var, then dev default
            self._master_key = self._resolve_master_key()

        if len(self._master_key) != 32:
            raise ValueError("Master key must be 32 bytes (64 hex chars)")

        self._data_keys: dict[str, list[DataKey]] = {}

    @staticmethod
    def _resolve_master_key() -> bytes:
        """Resolve master key: KMS > env var > dev default."""
        # Try to unwrap via KMS if configured
        kms_provider = os.environ.get("BUTLER_KMS_PROVIDER", "")
        encrypted_key_b64 = os.environ.get("BUTLER_ENCRYPTION_MASTER_KEY_ENCRYPTED", "")

        if kms_provider and encrypted_key_b64:
            try:
                import asyncio
                from butler.tenants.kms import get_kms_client
                kms = get_kms_client()
                if kms.is_available:
                    encrypted_key = __import__("base64").b64decode(encrypted_key_b64)
                    # Run async decrypt in a sync context (startup only)
                    loop = asyncio.new_event_loop()
                    try:
                        plaintext = loop.run_until_complete(
                            kms.decrypt(encrypted_key)
                        )
                        return plaintext
                    finally:
                        loop.close()
            except Exception:
                pass  # Fall through to env var

        # Direct env var (dev or non-KMS prod)
        key_hex = os.environ.get("BUTLER_ENCRYPTION_MASTER_KEY", "00" * 32)
        return bytes.fromhex(key_hex)

    def get_or_create_data_key(self, tenant_id: str) -> DataKey:
        """Get the active data key for a tenant, creating one if needed."""
        keys = self._data_keys.get(tenant_id, [])

        # Return active key if exists
        for key in keys:
            if key.is_active:
                return key

        # Create new key
        new_key = DataKey(
            key_id=f"dk-{tenant_id}-{len(keys) + 1}",
            key_material=os.urandom(32),
        )
        self._data_keys.setdefault(tenant_id, []).append(new_key)
        return new_key

    def encrypt_field(self, tenant_id: str, plaintext: str) -> str:
        """
        Encrypt a single PII field.

        Returns a base64-encoded ciphertext with embedded nonce and key_id.
        Format: base64(key_id + ":" + nonce + ciphertext_with_tag)
        """
        if not plaintext:
            return ""

        key = self.get_or_create_data_key(tenant_id)
        nonce = os.urandom(self.GCM_NONCE_SIZE)

        cipher = AES.new(key.key_material, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode("utf-8"))

        # Package: key_id (variable) + ":" + nonce (12) + ciphertext + tag (16)
        package = f"{key.key_id}:".encode() + nonce + ciphertext + tag
        return base64.b64encode(package).decode("ascii")

    def decrypt_field(self, tenant_id: str, encrypted: str) -> str:
        """Decrypt a PII field encrypted with encrypt_field()."""
        if not encrypted:
            return ""

        try:
            package = base64.b64decode(encrypted)
        except Exception:
            return ""  # Not encrypted or corrupted

        # Split key_id from the rest
        colon_idx = package.index(b":")
        key_id = package[:colon_idx].decode()
        nonce = package[colon_idx + 1:colon_idx + 1 + self.GCM_NONCE_SIZE]
        ciphertext_with_tag = package[colon_idx + 1 + self.GCM_NONCE_SIZE:]

        # Find the key
        keys = self._data_keys.get(tenant_id, [])
        data_key = None
        for k in keys:
            if k.key_id == key_id:
                data_key = k
                break

        if data_key is None:
            return ""

        cipher = AES.new(data_key.key_material, AES.MODE_GCM, nonce=nonce)
        plaintext = cipher.decrypt_and_verify(
            ciphertext_with_tag[:-self.GCM_TAG_SIZE],
            ciphertext_with_tag[-self.GCM_TAG_SIZE:],
        )
        return plaintext.decode("utf-8")

    def encrypt_dict(
        self, tenant_id: str, data: dict, sensitive_keys: set[str]
    ) -> dict:
        """Encrypt sensitive keys in a dict, returning a new dict."""
        result = {**data}
        for key in sensitive_keys:
            if key in result and result[key]:
                result[key] = self.encrypt_field(tenant_id, str(result[key]))
        return result

    def decrypt_dict(
        self, tenant_id: str, data: dict, sensitive_keys: set[str]
    ) -> dict:
        """Decrypt sensitive keys in a dict, returning a new dict."""
        result = {**data}
        for key in sensitive_keys:
            if key in result and result[key]:
                result[key] = self.decrypt_field(tenant_id, str(result[key]))
        return result


# Global singleton
_encryption: TenantEncryption | None = None


def get_encryption() -> TenantEncryption:
    global _encryption
    if _encryption is None:
        _encryption = TenantEncryption()
    return _encryption

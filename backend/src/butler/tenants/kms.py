"""
Key Management Service abstraction for master key protection.

Production: wraps master key via cloud KMS (Aliyun KMS / AWS KMS).
Development: local AES key from environment variable (bootstrap mode).

Flow:
  1. App starts → calls KMS decrypt on the encrypted master key blob
  2. KMS returns plaintext master key (never written to disk)
  3. Master key decrypts per-tenant data keys (envelope encryption)
  4. Data keys encrypt PII fields

Key rotation:
  - Master key: re-wrap with new KMS key, update encrypted blob
  - Data keys: create new version, re-encrypt fields with new DK
"""

from __future__ import annotations

import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol


# ── KMS Client Interface ──

class KmsClient(ABC):
    """Abstract KMS client for master key operations."""

    @abstractmethod
    async def decrypt(self, ciphertext_blob: bytes, key_id: str = "") -> bytes:
        """Decrypt a ciphertext blob using the KMS key. Returns plaintext."""
        ...

    @abstractmethod
    async def encrypt(self, plaintext: bytes, key_id: str = "") -> bytes:
        """Encrypt plaintext with the KMS key. Returns ciphertext blob."""
        ...

    @abstractmethod
    async def generate_data_key(self, key_id: str = "") -> tuple[bytes, bytes]:
        """Generate a data key. Returns (plaintext, encrypted) pair."""
        ...

    @abstractmethod
    async def re_encrypt(self, ciphertext_blob: bytes, source_key_id: str, dest_key_id: str) -> bytes:
        """Re-encrypt ciphertext from old key to new key (for rotation)."""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether the KMS backend is reachable."""
        ...


# ── Local (Dev) Implementation ──

class LocalKmsClient(KmsClient):
    """
    Development KMS using a local AES-256 key.
    Stores encrypted blobs as AES-GCM(key=local_master, plaintext).
    NOT for production — master key is in env var / memory.
    """

    def __init__(self) -> None:
        key_hex = os.environ.get("BUTLER_ENCRYPTION_MASTER_KEY", "00" * 32)
        self._key = bytes.fromhex(key_hex)

    async def decrypt(self, ciphertext_blob: bytes, key_id: str = "") -> bytes:
        from Crypto.Cipher import AES
        nonce = ciphertext_blob[:12]
        tag = ciphertext_blob[-16:]
        ciphertext = ciphertext_blob[12:-16]
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        return cipher.decrypt_and_verify(ciphertext, tag)

    async def encrypt(self, plaintext: bytes, key_id: str = "") -> bytes:
        from Crypto.Cipher import AES
        nonce = os.urandom(12)
        cipher = AES.new(self._key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(plaintext)
        return nonce + ciphertext + tag

    async def generate_data_key(self, key_id: str = "") -> tuple[bytes, bytes]:
        dk = os.urandom(32)
        encrypted = await self.encrypt(dk)
        return dk, encrypted

    async def re_encrypt(self, ciphertext_blob: bytes, source_key_id: str, dest_key_id: str) -> bytes:
        pt = await self.decrypt(ciphertext_blob)
        return await self.encrypt(pt)

    @property
    def is_available(self) -> bool:
        return True


# ── Aliyun KMS Implementation ──

class AliyunKmsClient(KmsClient):
    """
    Aliyun (阿里云) KMS client.
    Requires: pip install alibabacloud_kms20160120
    Env: ALIBABA_CLOUD_ACCESS_KEY_ID, ALIBABA_CLOUD_ACCESS_KEY_SECRET
    """

    def __init__(self, region: str = "cn-shanghai") -> None:
        self._region = region
        self._client = None
        self._available = False

        access_key = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_ID", "")
        secret = os.environ.get("ALIBABA_CLOUD_ACCESS_KEY_SECRET", "")
        if access_key and secret:
            try:
                # Lazy import — only if alibabacloud SDK is installed
                from alibabacloud_kms20160120.client import Client
                from alibabacloud_kms20160120 import models as kms_models
                from alibabacloud_tea_openapi import models as open_api_models
                config = open_api_models.Config(
                    access_key_id=access_key,
                    access_key_secret=secret,
                    region_id=region,
                )
                self._client = Client(config)
                self._kms_models = kms_models
                self._available = True
            except ImportError:
                pass

    async def decrypt(self, ciphertext_blob: bytes, key_id: str = "") -> bytes:
        if not self._client:
            raise RuntimeError("Aliyun KMS client not initialized")
        req = self._kms_models.DecryptRequest(
            ciphertext_blob=base64.b64encode(ciphertext_blob).decode(),
        )
        resp = await self._client.decrypt_async(req)
        return base64.b64decode(resp.body.plaintext)

    async def encrypt(self, plaintext: bytes, key_id: str = "") -> bytes:
        if not self._client:
            raise RuntimeError("Aliyun KMS client not initialized")
        kid = key_id or os.environ.get("ALIBABA_CLOUD_KMS_KEY_ID", "")
        req = self._kms_models.EncryptRequest(
            key_id=kid,
            plaintext=base64.b64encode(plaintext).decode(),
        )
        resp = await self._client.encrypt_async(req)
        return base64.b64decode(resp.body.ciphertext_blob)

    async def generate_data_key(self, key_id: str = "") -> tuple[bytes, bytes]:
        if not self._client:
            raise RuntimeError("Aliyun KMS client not initialized")
        kid = key_id or os.environ.get("ALIBABA_CLOUD_KMS_KEY_ID", "")
        req = self._kms_models.GenerateDataKeyRequest(
            key_id=kid,
            key_spec="AES_256",
        )
        resp = await self._client.generate_data_key_async(req)
        pt = base64.b64decode(resp.body.plaintext)
        ct = base64.b64decode(resp.body.ciphertext_blob)
        return pt, ct

    async def re_encrypt(self, ciphertext_blob: bytes, source_key_id: str, dest_key_id: str) -> bytes:
        pt = await self.decrypt(ciphertext_blob, source_key_id)
        return await self.encrypt(pt, dest_key_id)

    @property
    def is_available(self) -> bool:
        return self._available and self._client is not None


# ── AWS KMS Implementation ──

class AwsKmsClient(KmsClient):
    """
    AWS KMS client.
    Requires: pip install boto3
    Uses default AWS credential chain (env, instance profile, etc.)
    """

    def __init__(self, region: str = "us-east-1") -> None:
        self._region = region
        self._client = None
        self._available = False

        try:
            import boto3
            self._client = boto3.client("kms", region_name=region)
            self._available = True
        except Exception:
            pass

    async def decrypt(self, ciphertext_blob: bytes, key_id: str = "") -> bytes:
        if not self._client:
            raise RuntimeError("AWS KMS client not initialized")
        import asyncio
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.decrypt(CiphertextBlob=ciphertext_blob),
        )
        return resp["Plaintext"]

    async def encrypt(self, plaintext: bytes, key_id: str = "") -> bytes:
        if not self._client:
            raise RuntimeError("AWS KMS client not initialized")
        kid = key_id or os.environ.get("AWS_KMS_KEY_ID", "")
        import asyncio
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.encrypt(KeyId=kid, Plaintext=plaintext),
        )
        return resp["CiphertextBlob"]

    async def generate_data_key(self, key_id: str = "") -> tuple[bytes, bytes]:
        if not self._client:
            raise RuntimeError("AWS KMS client not initialized")
        kid = key_id or os.environ.get("AWS_KMS_KEY_ID", "")
        import asyncio
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.generate_data_key(KeyId=kid, KeySpec="AES_256"),
        )
        return resp["Plaintext"], resp["CiphertextBlob"]

    async def re_encrypt(self, ciphertext_blob: bytes, source_key_id: str, dest_key_id: str) -> bytes:
        import asyncio
        loop = asyncio.get_running_loop()
        resp = await loop.run_in_executor(
            None,
            lambda: self._client.re_encrypt(
                CiphertextBlob=ciphertext_blob,
                SourceKeyId=source_key_id,
                DestinationKeyId=dest_key_id,
            ),
        )
        return resp["CiphertextBlob"]

    @property
    def is_available(self) -> bool:
        return self._available and self._client is not None


# ── KMS Factory ──

_KMS_CLIENT: KmsClient | None = None


def get_kms_client() -> KmsClient:
    """Get the KMS client based on environment configuration."""
    global _KMS_CLIENT
    if _KMS_CLIENT is not None:
        return _KMS_CLIENT

    kms_provider = os.environ.get("BUTLER_KMS_PROVIDER", "local").lower()

    if kms_provider == "aliyun":
        region = os.environ.get("ALIBABA_CLOUD_REGION", "cn-shanghai")
        client = AliyunKmsClient(region)
        if client.is_available:
            _KMS_CLIENT = client
            return _KMS_CLIENT

    if kms_provider == "aws":
        region = os.environ.get("AWS_REGION", "us-east-1")
        client = AwsKmsClient(region)
        if client.is_available:
            _KMS_CLIENT = client
            return _KMS_CLIENT

    # Fallback to local
    _KMS_CLIENT = LocalKmsClient()
    return _KMS_CLIENT


# ── Key Rotation ──

@dataclass
class KeyRotationRecord:
    """Record of a key rotation event."""
    rotated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    old_key_id: str = ""
    new_key_id: str = ""
    tenant_id: str = ""
    fields_rotated: int = 0


async def rotate_master_key(new_key_id: str = "") -> KeyRotationRecord:
    """
    Rotate the master key: re-wrap encrypted data keys with new KMS key.
    In production, this is a background job that runs periodically.
    """
    kms = get_kms_client()
    old_key = os.environ.get("BUTLER_KMS_KEY_ID", "")

    record = KeyRotationRecord(
        old_key_id=old_key,
        new_key_id=new_key_id,
    )

    # In production: iterate all tenant data keys, re-encrypt with new key
    # For MVP: log the rotation event
    return record

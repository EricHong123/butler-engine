"""
企业微信 message encryption/decryption (AES-256-CBC + PKCS#7).

Protocol: https://developer.work.weixin.qq.com/document/path/90968
"""

from __future__ import annotations

import base64
import hashlib
import random
import string
import struct
import time
from xml.etree import ElementTree as ET

from Crypto.Cipher import AES


class WeChatCrypto:
    """
    Handles 企业微信 message encrypt/decrypt.

    Args:
        token: WeChat verification token
        encoding_aes_key: 43-character Base64-encoded AES key
        corp_id: WeChat Corp ID
    """

    BLOCK_SIZE = 32  # AES-256

    def __init__(self, token: str, encoding_aes_key: str, corp_id: str) -> None:
        self.token = token
        self.corp_id = corp_id
        self.aes_key = base64.b64decode(encoding_aes_key + "=")

        if len(self.aes_key) != 32:
            raise ValueError(f"Invalid AES key length: {len(self.aes_key)}, expected 32")

    def verify_signature(
        self, msg_signature: str, timestamp: str, nonce: str, echostr: str
    ) -> bool:
        """Verify URL callback signature."""
        params = sorted([self.token, timestamp, nonce, echostr])
        sha1 = hashlib.sha1("".join(params).encode()).hexdigest()
        return sha1 == msg_signature

    def decrypt(self, encrypted_xml: str) -> str:
        """
        Decrypt an encrypted XML message from 企业微信.

        Returns the decrypted plaintext XML string.
        """
        root = ET.fromstring(encrypted_xml)
        encrypted = root.find("Encrypt")
        if encrypted is None or encrypted.text is None:
            raise ValueError("No <Encrypt> element found in XML")
        return self._decrypt_text(encrypted.text)

    def encrypt(self, plaintext: str, nonce: str) -> str:
        """
        Encrypt a plaintext XML response for 企业微信.

        Returns the encrypted XML string ready to send back.
        """
        encrypted = self._encrypt_text(plaintext)
        timestamp = str(int(time.time()))
        signature = self._sign(timestamp, nonce, encrypted)

        return (
            "<xml>\n"
            f"<Encrypt><![CDATA[{encrypted}]]></Encrypt>\n"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>\n"
            f"<TimeStamp>{timestamp}</TimeStamp>\n"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>\n"
            "</xml>"
        )

    def decrypt_echostr(self, echostr: str) -> str:
        """Decrypt the echostr parameter during URL verification."""
        return self._decrypt_text(echostr)

    # ── Private ──

    def _decrypt_text(self, encrypted: str) -> str:
        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv=self.aes_key[:16])
        ciphertext = base64.b64decode(encrypted)
        plaintext = cipher.decrypt(ciphertext)

        # Unpad PKCS#7
        pad_len = plaintext[-1]
        if pad_len < 1 or pad_len > self.BLOCK_SIZE:
            raise ValueError(f"Invalid PKCS#7 padding: {pad_len}")
        plaintext = plaintext[:-pad_len]

        # Parse: random(16) + msg_len(4) + msg + corpid
        if len(plaintext) < 20:
            raise ValueError("Decrypted message too short")

        msg_len = struct.unpack("!I", plaintext[16:20])[0]
        msg = plaintext[20:20 + msg_len].decode("utf-8")
        received_corpid = plaintext[20 + msg_len:].decode("utf-8")

        if received_corpid != self.corp_id:
            raise ValueError(
                f"CorpID mismatch: expected {self.corp_id}, got {received_corpid}"
            )

        return msg

    def _encrypt_text(self, plaintext: str) -> str:
        """Encrypt plaintext and return Base64-encoded ciphertext."""
        # Format: random(16) + msg_len(4) + msg_bytes + corpid_bytes
        random_bytes = bytes(random.randint(0, 255) for _ in range(16))
        msg_bytes = plaintext.encode("utf-8")
        msg_len = struct.pack("!I", len(msg_bytes))
        corp_bytes = self.corp_id.encode("utf-8")

        plain = random_bytes + msg_len + msg_bytes + corp_bytes

        # PKCS#7 padding
        pad_len = self.BLOCK_SIZE - (len(plain) % self.BLOCK_SIZE)
        plain += bytes([pad_len] * pad_len)

        cipher = AES.new(self.aes_key, AES.MODE_CBC, iv=self.aes_key[:16])
        ciphertext = cipher.encrypt(plain)

        return base64.b64encode(ciphertext).decode()

    def _sign(self, timestamp: str, nonce: str, encrypted: str) -> str:
        params = sorted([self.token, timestamp, nonce, encrypted])
        return hashlib.sha1("".join(params).encode()).hexdigest()

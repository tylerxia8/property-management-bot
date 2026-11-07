import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_VERSION = 1


def encrypt_text(plaintext: str, key: bytes) -> tuple[bytes, bytes, int]:
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
    return ciphertext, nonce, KEY_VERSION


def decrypt_text(ciphertext: bytes, nonce: bytes, key: bytes) -> str:
    return AESGCM(key).decrypt(nonce, ciphertext, None).decode("utf-8")

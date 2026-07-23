"""Criptografia simetrica (Fernet/AES) para guardar o .pfx e a senha do
certificado digital em repouso. Nunca sao gravados em texto puro no banco.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet

SECRET_KEY_PATH = Path(__file__).resolve().parent.parent / "data" / "secret.key"


def _load_or_create_key() -> bytes:
    env_key = os.getenv("SECRET_KEY")
    if env_key:
        return env_key.encode() if isinstance(env_key, str) else env_key

    if SECRET_KEY_PATH.exists():
        return SECRET_KEY_PATH.read_bytes()

    key = Fernet.generate_key()
    SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SECRET_KEY_PATH.write_bytes(key)
    return key


def get_fernet() -> Fernet:
    return Fernet(_load_or_create_key())


def encriptar(dado: bytes) -> bytes:
    return get_fernet().encrypt(dado)


def decriptar(token: bytes) -> bytes:
    return get_fernet().decrypt(token)

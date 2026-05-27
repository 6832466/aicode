"""AES-256-GCM 字符串加解密工具。依赖: pip install cryptography"""

import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

_MAGIC = b"SYCE"
_SALT_LEN = 16
_IV_LEN = 12
_KDF_ITERATIONS = 100000
_VERSION = 1


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_KDF_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def _aes_encrypt(plain: bytes, password: str) -> bytes:
    salt = os.urandom(_SALT_LEN)
    iv = os.urandom(_IV_LEN)
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(iv, plain, None)
    result = bytearray()
    result.extend(_MAGIC)
    result.append(_VERSION)
    result.extend(salt)
    result.extend(iv)
    result.extend(ciphertext)
    return bytes(result)


def _aes_decrypt(encrypted: bytes, password: str) -> bytes:
    if encrypted[:4] != _MAGIC:
        raise ValueError("数据不是有效的加密格式（魔数 'SYCE' 不匹配）")
    offset = 4
    version = encrypted[offset]
    offset += 1
    if version != _VERSION:
        raise ValueError(f"不支持的加密版本: {version}")
    salt = encrypted[offset : offset + _SALT_LEN]
    offset += _SALT_LEN
    iv = encrypted[offset : offset + _IV_LEN]
    offset += _IV_LEN
    ciphertext = encrypted[offset:]
    key = _derive_key(password, salt)
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(iv, ciphertext, None)
    except Exception:
        raise ValueError("解密失败：密码错误或数据已损坏")


def _is_encrypted(data: bytes) -> bool:
    return data[:4] == _MAGIC


class CookieEncryptor:
    """AES-256-GCM 字符串加解密"""

    @staticmethod
    def encrypt_string(text: str, password: str) -> str:
        """加密字符串

        Args:
            text: 明文字符串
            password: 加密密码

        Returns:
            base64 字符串
        """
        plain = text.encode("utf-8")
        encrypted = _aes_encrypt(plain, password)
        return base64.b64encode(encrypted).decode("ascii")

    @staticmethod
    def decrypt_string(encoded: str, password: str) -> str:
        """解密字符串

        Args:
            encoded: encrypt_string 输出的 base64 字符串
            password: 加密密码

        Returns:
            明文字符串
        """
        raw = base64.b64decode(encoded.strip())
        if not _is_encrypted(raw):
            raise ValueError("数据不是有效的加密格式")
        decrypted = _aes_decrypt(raw, password)
        return decrypted.decode("utf-8")


# =====================================================================
# 自测
# =====================================================================
if __name__ == "__main__":
    enc = CookieEncryptor.encrypt_string("师父的起飞之路", password="test123")
    print(f"加密: {enc}")
    dec = CookieEncryptor.decrypt_string(enc, password="test123")
    print(f"解密: {dec}")
    assert dec == "师父的起飞之路"

    # 错误密码
    try:
        CookieEncryptor.decrypt_string(enc, password="wrong")
        assert False
    except ValueError as e:
        print(f"错误密码: ✓ ({e})")

    print("\n全部测试通过!")

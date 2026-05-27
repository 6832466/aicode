"""
CookieEncryptor —— Cookie 数据加密/解密工具类 (Python 版)
=========================================================

封装 sync-your-cookie 的完整编解码管线:
    CookiesMap → protobuf → raw-deflate → gzip → base64 → [AES-256-GCM → base64]

依赖:
    pip install cryptography protobuf

用法:
    from cookie_encryptor import CookieEncryptor

    # 解密（从云端拉取后还原 cookie）
    encryptor = CookieEncryptor(password="my-secret")
    cookies_map = encryptor.decode(encoded_string)

    # 加密
    encoded = encryptor.encode(cookies_map)

    # 不加密（仅压缩编码）
    no_encrypt = CookieEncryptor()
    compressed = no_encrypt.encode(cookies_map)
"""

import base64
import gzip
import json
import struct
import zlib
from typing import Any, Dict, List, Optional, Union

# ------- AES & KDF -----------------------------------------------------------
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

# ------- Protobuf dynamic loading ---------------------------------------------
from google.protobuf import descriptor_pb2, descriptor_pool, message_factory, json_format
from google.protobuf.message import Message

# =====================================================================
# 内置 FileDescriptorSet — 等同于 cookie.proto 的编译结果，无需外部文件
# =====================================================================
_FDS_B64 = (
    "CrEECgxjb29raWUucHJvdG8irQEKBkNvb2tpZRIMCgZkb21haW4YASgJEgoKBG5hbWUYAi"
    "gJEg0KB3N0b3JlSWQYAygJEgsKBXZhbHVlGAQoCRINCgdzZXNzaW9uGAUoCBIOCghob3N0"
    "T25seRgGKAgSFAoOZXhwaXJhdGlvbkRhdGUYBygCEgoKBHBhdGgYCCgJEg4KCGh0dHBPbm"
    "x5GAkoCBIMCgZzZWN1cmUYCigIEg4KCHNhbWVTaXRlGAsoCSIqChBMb2NhbFN0b3JhZ2VJ"
    "dGVtEgkKA2tleRgBKAkSCwoFdmFsdWUYAigJIosBCgxEb21haW5Db29raWUSEAoKY3JlYX"
    "RlVGltZRgBKAMSEAoKdXBkYXRlVGltZRgCKAMSDwoJdXNlckFnZW50GAcoCRIYCgdjb29r"
    "aWVzGAUgAygLMgcuQ29va2llEiwKEWxvY2FsU3RvcmFnZUl0ZW1zGAYgAygLMhEuTG9jYW"
    "xTdG9yYWdlSXRlbSKuAQoKQ29va2llc01hcBIQCgpjcmVhdGVUaW1lGAEoAxIQCgp1cGRh"
    "dGVUaW1lGAIoAxI5Cg9kb21haW5Db29raWVNYXAYBSADKAsyIC5Db29raWVzTWFwLkRvbW"
    "FpbkNvb2tpZU1hcEVudHJ5GkEKFERvbWFpbkNvb2tpZU1hcEVudHJ5EgkKA2tleRgBKAkS"
    "GgoFdmFsdWUYAigLMg0uRG9tYWluQ29va2llOgI4AWIGcHJvdG8z"
)


class _Proto:
    """protobuf 消息类型的延迟加载容器"""

    Cookie: type = None
    LocalStorageItem: type = None
    DomainCookie: type = None
    CookiesMap: type = None

    _loaded = False

    @classmethod
    def _load(cls):
        if cls._loaded:
            return
        fds = descriptor_pb2.FileDescriptorSet()
        fds.ParseFromString(base64.b64decode(_FDS_B64))
        pool = descriptor_pool.DescriptorPool()
        for fdp in fds.file:
            pool.Add(fdp)
        cls.Cookie = message_factory.GetMessageClass(pool.FindMessageTypeByName("Cookie"))
        cls.LocalStorageItem = message_factory.GetMessageClass(pool.FindMessageTypeByName("LocalStorageItem"))
        cls.DomainCookie = message_factory.GetMessageClass(pool.FindMessageTypeByName("DomainCookie"))
        cls.CookiesMap = message_factory.GetMessageClass(pool.FindMessageTypeByName("CookiesMap"))
        cls._loaded = True


def _ensure_proto():
    _Proto._load()


# =====================================================================
# Base64
# =====================================================================

def _b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.b64decode(data.strip())


# =====================================================================
# Gzip + Raw Deflate 压缩 / 解压
# =====================================================================

def _compress(plain: bytes) -> bytes:
    """管线: zlib-deflate → gzip（与 pako.deflate + CompressionStream('gzip') 等价）

    pako.deflate() 在 v2.x 默认输出 zlib 格式（含 78 9c 头部），
    而非 raw deflate，因此 Python 端也使用 zlib 格式以保持兼容。"""
    deflated = zlib.compress(plain, level=9)
    return gzip.compress(deflated, compresslevel=9)


def _decompress(compressed: bytes) -> bytes:
    """管线: gzip 解压 → zlib-inflate（逆操作）"""
    gzip_decoded = gzip.decompress(compressed)
    return zlib.decompress(gzip_decoded)


# =====================================================================
# AES-256-GCM 加密 / 解密
# =====================================================================

_MAGIC = b"SYCE"
_SALT_LEN = 16
_IV_LEN = 12
_KDF_ITERATIONS = 100000
_VERSION = 1


def _aes_encrypt(plain: bytes, password: str) -> bytes:
    """AES-256-GCM 加密，输出格式: MAGIC(4) + VERSION(1) + SALT(16) + IV(12) + CIPHERTEXT"""
    salt = __import__("os").urandom(_SALT_LEN)
    iv = __import__("os").urandom(_IV_LEN)
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
    """AES-256-GCM 解密，输入需符合 _aes_encrypt 的输出格式"""
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


def _derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=_KDF_ITERATIONS)
    return kdf.derive(password.encode("utf-8"))


def _is_encrypted(data: bytes) -> bool:
    return data[:4] == _MAGIC


# =====================================================================
# Protobuf ↔ 字典 互转
# =====================================================================

def _msg_to_dict(msg: Message) -> dict:
    """将 protobuf Message 转为纯 Python dict（int64 Long 自动转 int）"""
    result = json_format.MessageToDict(msg, preserving_proto_field_name=True)
    _fix_int64(result)
    return result


def _fix_int64(obj):
    """将 MessageToDict 产生的 int64 字符串转回 int"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("createTime", "updateTime") and isinstance(v, str):
                obj[k] = int(v)
            else:
                _fix_int64(v)
    elif isinstance(obj, list):
        for item in obj:
            _fix_int64(item)


def _dict_to_cookies_map(data: dict) -> Message:
    """将 dict 转为 CookiesMap protobuf Message（使用 ParseDict 自动处理 map 字段）"""
    _ensure_proto()
    return json_format.ParseDict(data, _Proto.CookiesMap())


def _protobuf_encode(data: dict) -> bytes:
    """dict → CookiesMap protobuf 二进制"""
    msg = _dict_to_cookies_map(data)
    return msg.SerializeToString()


def _protobuf_decode(binary: bytes) -> dict:
    """CookiesMap protobuf 二进制 → dict"""
    _ensure_proto()
    msg = _Proto.CookiesMap()
    msg.ParseFromString(binary)
    return _msg_to_dict(msg)


# =====================================================================
# 主类
# =====================================================================

class CookieEncryptor:
    """Cookie 数据加解密工具

    参数:
        password: 加密密码，为空时不加密仅压缩
    """

    def __init__(self, password: str = ""):
        self.password = password

    # ---------- 编码 ----------

    def encode(self, cookies_map: dict, *,
               password: Optional[str] = None,
               protobuf: bool = True) -> str:
        """CookiesMap dict → 云端存储字符串

        Args:
            cookies_map: 符合 ICookiesMap 结构的 dict
            password:    加密密码，默认使用实例密码
            protobuf:    True 则 protobuf 编码，False 则返回 JSON 字符串（不加密）

        Returns:
            base64 字符串，可直接写入 Cloudflare KV / GitHub Gist
        """
        pwd = password if password is not None else self.password

        if not protobuf:
            if pwd:
                import warnings
                warnings.warn("JSON 模式不支持加密，已忽略 password")
            return json.dumps(cookies_map, ensure_ascii=False)

        proto_binary = _protobuf_encode(cookies_map)
        compressed = _compress(proto_binary)
        inner_b64 = _b64encode(compressed)

        if pwd:
            raw = _b64decode(inner_b64)
            encrypted = _aes_encrypt(raw, pwd)
            return _b64encode(encrypted)

        return inner_b64

    # ---------- 解码 ----------

    def decode(self, encoded_data: str, *,
               password: Optional[str] = None) -> dict:
        """云端存储字符串 → CookiesMap dict

        自动检测格式：JSON / protobuf / AES-GCM 加密。
        无需手动指定数据类型。

        Args:
            encoded_data: 云端存储的原始字符串
            password:     加密密码，默认使用实例密码

        Returns:
            CookiesMap dict
        """
        pwd = password if password is not None else self.password

        if encoded_data.strip().startswith("{"):
            return json.loads(encoded_data)

        raw = _b64decode(encoded_data)

        if _is_encrypted(raw):
            if not pwd:
                raise ValueError("检测到加密数据但未提供密码，请传入 password 参数。")
            raw = _aes_decrypt(raw, pwd)

        try:
            decompressed = _decompress(raw)
            return _protobuf_decode(decompressed)
        except Exception as exc:
            raise ValueError(
                f"数据解压或解码失败: {exc}。"
                f"如果数据未使用 protobuf 编码，请使用 decode_json() 方法。"
            )

    # ---------- JSON ----------

    @staticmethod
    def decode_json(json_data: str) -> dict:
        """解码 JSON 格式的 Cookie 数据（不使用 protobuf 时）"""
        return json.loads(json_data)

    # ---------- 类型检测 ----------

    @staticmethod
    def detect_type(data: str) -> str:
        """检测编码类型

        Returns:
            'json' | 'encrypted' | 'protobuf' | 'unknown'
        """
        if not data or not isinstance(data, str):
            return "unknown"
        trimmed = data.strip()
        if trimmed.startswith("{"):
            return "json"
        try:
            raw = _b64decode(trimmed)
            if _is_encrypted(raw):
                return "encrypted"
            return "protobuf"
        except Exception:
            return "unknown"


# =====================================================================
# 便捷函数
# =====================================================================

def encrypt_cookies(cookies_map: dict, password: str = "") -> str:
    """快速加密（编码）Cookie 数据"""
    return CookieEncryptor(password=password).encode(cookies_map)


def decrypt_cookies(encoded_data: str, password: str = "") -> dict:
    """快速解密（解码）Cookie 数据"""
    return CookieEncryptor(password=password).decode(encoded_data)


# =====================================================================
# 自测（python cookie_encryptor.py）
# =====================================================================
if __name__ == "__main__":
    sample = {
        "createTime": 1700000000000,
        "updateTime": 1700000001000,
        "domainCookieMap": {
            "example.com": {
                "createTime": 1690000000000,
                "updateTime": 1700000000000,
                "userAgent": "Mozilla/5.0 (Windows NT 10.0)",
                "cookies": [
                    {"domain": ".example.com", "name": "session", "value": "abc123",
                     "path": "/", "secure": True, "httpOnly": True, "sameSite": "lax"},
                    {"domain": ".example.com", "name": "token",
                     "value": "eyJhbGciOiJIUzI1NiJ9.xxx", "path": "/",
                     "secure": True, "httpOnly": True},
                ],
                "localStorageItems": [
                    {"key": "theme", "value": "dark"},
                    {"key": "lang", "value": "zh-CN"},
                ],
            },
        },
    }

    password = "test-1234"

    # 1. 加密 + 解密
    e = CookieEncryptor(password=password)
    enc = e.encode(sample)
    assert CookieEncryptor.detect_type(enc) == "encrypted", "detectType fail"
    dec = e.decode(enc)
    assert dec["domainCookieMap"]["example.com"]["cookies"][0]["value"] == "abc123"
    print("1. 加密→解密: ✓")

    # 2. 不加密
    e2 = CookieEncryptor()
    enc2 = e2.encode(sample)
    assert CookieEncryptor.detect_type(enc2) == "protobuf", f"detectType fail: {CookieEncryptor.detect_type(enc2)}"
    dec2 = e2.decode(enc2)
    assert len(dec2["domainCookieMap"]["example.com"]["cookies"]) == 2
    print("2. 不加密压缩: ✓")

    # 3. JSON 模式
    enc3 = e2.encode(sample, protobuf=False)
    assert CookieEncryptor.detect_type(enc3) == "json"
    dec3 = CookieEncryptor.decode_json(enc3)
    assert dec3["domainCookieMap"]["example.com"]["cookies"][1]["value"] == "eyJhbGciOiJIUzI1NiJ9.xxx"
    print("3. JSON 模式: ✓")

    # 4. 便捷函数
    enc4 = encrypt_cookies(sample, password)
    dec4 = decrypt_cookies(enc4, password)
    assert dec4["domainCookieMap"]["example.com"]["localStorageItems"][0]["value"] == "dark"
    print("4. 便捷函数: ✓")

    # 5. 错误密码
    try:
        e.decode(enc, password="wrong")
        assert False, "should raise"
    except ValueError as ex:
        assert "密码错误" in str(ex) or "密钥" in str(ex)
        print(f"5. 错误密码: ✓ ({ex})")

    # 6. detectType
    assert CookieEncryptor.detect_type("") == "unknown"
    assert CookieEncryptor.detect_type("{}") == "json"
    assert CookieEncryptor.detect_type(None) == "unknown"
    print("6. detectType 边界: ✓")

    # 7. 多次往返
    for i in range(3):
        enc_x = e.encode(sample)
        dec_x = e.decode(enc_x)
        assert dec_x["domainCookieMap"]["example.com"]["cookies"][0]["value"] == "abc123"
    print("7. 多次往返: ✓")

    print("\n全部测试通过!")

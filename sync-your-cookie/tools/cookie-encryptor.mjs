/**
 * CookieEncryptor — Cookie 数据加密/解密工具类
 *
 * 封装 sync-your-cookie 的完整编解码管线：
 *   CookiesMap → protobuf → deflate → gzip → base64 → [AES-256-GCM → base64]
 *
 * 用法:
 *   import { CookieEncryptor } from './cookie-encryptor.mjs';
 *
 *   // 加密（从扩展获取 cookie 数据后上传到云端）
 *   const encryptor = new CookieEncryptor({ password: 'my-secret' });
 *   const encoded = await encryptor.encode(cookiesMap);
 *
 *   // 解密（从云端拉取数据后还原 cookie）
 *   const cookiesMap = await encryptor.decode(encoded);
 *
 *   // 不加密（仅压缩编码）
 *   const noEncrypt = new CookieEncryptor();
 *   const compressed = await noEncrypt.encode(cookiesMap);
 *
 * 依赖: pako, protobufjs
 */

import pako from 'pako';
import protobuf from 'protobufjs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

// ─── 常量 ─────────────────────────────────────────────────────────────────

const __dirname = dirname(fileURLToPath(import.meta.url));
const DEFAULT_PROTO_FILE = resolve(__dirname, '..', 'packages', 'protobuf', 'proto', 'cookie.proto');

/** AES-GCM 加密魔数 "SYCE" */
const MAGIC_BYTES = new Uint8Array([0x53, 0x59, 0x43, 0x45]);
const SALT_LENGTH = 16;
const IV_LENGTH = 12;
const PBKDF2_ITERATIONS = 100000;
const ENCRYPTION_VERSION = 1;

const BASE64_CHARS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';

// ─── 类型定义 (JSDoc) ─────────────────────────────────────────────────────

/**
 * @typedef {Object} ICookie
 * @property {string} [domain]
 * @property {string} [name]
 * @property {string} [storeId]
 * @property {string} [value]
 * @property {boolean} [session]
 * @property {boolean} [hostOnly]
 * @property {number} [expirationDate]
 * @property {string} [path]
 * @property {boolean} [httpOnly]
 * @property {boolean} [secure]
 * @property {string} [sameSite]
 */

/**
 * @typedef {Object} ILocalStorageItem
 * @property {string} [key]
 * @property {string} [value]
 */

/**
 * @typedef {Object} IDomainCookie
 * @property {number|Long} [createTime]
 * @property {number|Long} [updateTime]
 * @property {ICookie[]} [cookies]
 * @property {ILocalStorageItem[]} [localStorageItems]
 * @property {string} [userAgent]
 */

/**
 * @typedef {Object} ICookiesMap
 * @property {number|Long} [createTime]
 * @property {number|Long} [updateTime]
 * @property {Object<string, IDomainCookie>} [domainCookieMap]
 */

// ─── Base64 编解码 ────────────────────────────────────────────────────────

function base64Encode(bytes) {
  let result = '';
  const len = bytes.byteLength;
  const remainder = len % 3;
  const mainLen = len - remainder;

  for (let i = 0; i < mainLen; i += 3) {
    const chunk = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    result += BASE64_CHARS[(chunk & 16515072) >> 18] + BASE64_CHARS[(chunk & 258048) >> 12] +
              BASE64_CHARS[(chunk & 4032) >> 6] + BASE64_CHARS[chunk & 63];
  }
  if (remainder === 1) {
    const chunk = bytes[mainLen];
    result += BASE64_CHARS[(chunk & 252) >> 2] + BASE64_CHARS[(chunk & 3) << 4] + '==';
  } else if (remainder === 2) {
    const chunk = (bytes[mainLen] << 8) | bytes[mainLen + 1];
    result += BASE64_CHARS[(chunk & 64512) >> 10] + BASE64_CHARS[(chunk & 1008) >> 4] +
              BASE64_CHARS[(chunk & 15) << 2] + '=';
  }
  return result;
}

function base64Decode(base64) {
  const binary = atob(base64.trim());
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

// ─── Gzip 压缩/解压 ───────────────────────────────────────────────────────

async function gzipCompress(data) {
  const stream = new Blob([data]).stream().pipeThrough(new CompressionStream('gzip'));
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  return new Uint8Array(await new Blob(chunks).arrayBuffer());
}

async function gzipDecompress(data) {
  const stream = new Blob([data]).stream().pipeThrough(new DecompressionStream('gzip'));
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(chunk);
  }
  return new Uint8Array(await new Blob(chunks).arrayBuffer());
}

// ─── AES-256-GCM 加密/解密 ───────────────────────────────────────────────

async function deriveKey(password, salt) {
  const encoder = new TextEncoder();
  const baseKey = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: PBKDF2_ITERATIONS, hash: 'SHA-256' },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

async function aesEncrypt(plainBytes, password) {
  const salt = crypto.getRandomValues(new Uint8Array(SALT_LENGTH));
  const iv = crypto.getRandomValues(new Uint8Array(IV_LENGTH));
  const key = await deriveKey(password, salt);
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, key, plainBytes);

  const result = new Uint8Array(4 + 1 + SALT_LENGTH + IV_LENGTH + ciphertext.byteLength);
  let offset = 0;
  result.set(MAGIC_BYTES, offset); offset += 4;
  result[offset] = ENCRYPTION_VERSION; offset += 1;
  result.set(salt, offset); offset += SALT_LENGTH;
  result.set(iv, offset); offset += IV_LENGTH;
  result.set(new Uint8Array(ciphertext), offset);
  return result;
}

async function aesDecrypt(encryptedBytes, password) {
  let offset = 0;

  const magic = encryptedBytes.slice(0, 4);
  if (!magic.every((b, i) => b === MAGIC_BYTES[i])) {
    throw new Error('数据不是有效的加密格式（魔数不匹配）');
  }
  offset += 4;

  const version = encryptedBytes[offset++];
  if (version !== ENCRYPTION_VERSION) {
    throw new Error(`不支持的加密版本: ${version}`);
  }

  const salt = encryptedBytes.slice(offset, offset + SALT_LENGTH);
  offset += SALT_LENGTH;
  const iv = encryptedBytes.slice(offset, offset + IV_LENGTH);
  offset += IV_LENGTH;
  const ciphertext = encryptedBytes.slice(offset);

  const key = await deriveKey(password, salt);
  try {
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
    return new Uint8Array(decrypted);
  } catch {
    throw new Error('解密失败：密码错误或数据已损坏');
  }
}

// ─── Protobuf 编解码 ─────────────────────────────────────────────────────

/**
 * @returns {Promise<protobuf.Type>}
 */
async function loadProto(protoFile) {
  const root = await protobuf.load(protoFile);
  return root.lookupType('CookiesMap');
}

/**
 * @param {ICookiesMap} cookiesMap
 * @param {protobuf.Type} [CookiesMapType]
 * @returns {Uint8Array}
 */
async function protobufEncode(cookiesMap, CookiesMapType) {
  const type = CookiesMapType || await loadProto(DEFAULT_PROTO_FILE);
  const invalid = type.verify(cookiesMap);
  if (invalid) throw new Error(`Protobuf 数据验证失败: ${invalid}`);
  const message = type.create(cookiesMap);
  return type.encode(message).finish();
}

/**
 * @param {Uint8Array} buffer
 * @param {protobuf.Type} [CookiesMapType]
 * @returns {Promise<ICookiesMap>}
 */
async function protobufDecode(buffer, CookiesMapType) {
  const type = CookiesMapType || await loadProto(DEFAULT_PROTO_FILE);
  const result = type.decode(buffer);
  return JSON.parse(JSON.stringify(result, (key, value) => {
    if (typeof value === 'object' && value !== null && typeof value.toNumber === 'function') {
      return value.toNumber();
    }
    return value;
  }));
}

// ─── 主类 ─────────────────────────────────────────────────────────────────

export class CookieEncryptor {
  /**
   * @param {Object} [options]
   * @param {string} [options.password] - 加密密码。不传则跳过 AES 加密，仅进行压缩编码
   * @param {string} [options.protoFile] - .proto 文件路径，默认使用项目内置的 cookie.proto
   */
  constructor(options = {}) {
    this.password = options.password || '';
    this.protoFile = options.protoFile || DEFAULT_PROTO_FILE;
    /** @type {protobuf.Type|null} */
    this._protoType = null;
  }

  /**
   * 加载 protobuf schema（惰性加载，首次使用时自动调用）
   * @returns {Promise<protobuf.Type>}
   */
  async _loadProto() {
    if (!this._protoType) {
      this._protoType = await loadProto(this.protoFile);
    }
    return this._protoType;
  }

  /**
   * 编码 CookiesMap 为云端存储格式。
   *
   * 管线: protobuf → deflate → gzip → base64 → [AES-GCM 加密 → base64]
   *
   * @param {ICookiesMap} cookiesMap - Cookie 数据
   * @param {Object} [options]
   * @param {string} [options.password] - 覆盖实例的密码
   * @param {boolean} [options.protobuf=true] - 是否使用 protobuf 编码（false 则返回 JSON 字符串，不加密）
   * @returns {Promise<string>} 云端存储格式的字符串
   */
  async encode(cookiesMap, options = {}) {
    const password = options.password ?? this.password;
    const useProtobuf = options.protobuf !== false;

    if (!useProtobuf) {
      if (password) {
        console.warn('[CookieEncryptor] JSON 模式不支持加密，已忽略 password 参数。请使用 protobuf 模式启用加密。');
      }
      return JSON.stringify(cookiesMap);
    }

    const protoType = await this._loadProto();
    const encoded = await protobufEncode(cookiesMap, protoType);
    const deflated = pako.deflate(encoded);
    const compressed = await gzipCompress(deflated);
    const innerBase64 = base64Encode(compressed);

    if (password) {
      const rawBytes = base64Decode(innerBase64);
      const encrypted = await aesEncrypt(rawBytes, password);
      return base64Encode(encrypted);
    }

    return innerBase64;
  }

  /**
   * 从云端存储格式解码为 CookiesMap。
   *
   * 自动检测并处理：JSON、protobuf、AES-GCM 加密。
   *
   * @param {string} encodedData - 云端存储的原始数据
   * @param {Object} [options]
   * @param {string} [options.password] - 覆盖实例的密码
   * @returns {Promise<ICookiesMap>} 解密后的 CookiesMap
   */
  async decode(encodedData, options = {}) {
    const password = options.password ?? this.password;
    let processed = encodedData;

    // JSON 格式（以 { 开头）
    if (processed.startsWith('{')) {
      return JSON.parse(processed);
    }

    // Base64 解码
    let rawBytes;
    try {
      rawBytes = base64Decode(processed);
    } catch {
      throw new Error('无法解码 base64，数据格式不正确');
    }

    // 检测并处理加密
    if (isEncrypted(rawBytes)) {
      if (!password) {
        throw new Error('检测到加密数据但未提供密码。请传入 password 参数。');
      }
      const decrypted = await aesDecrypt(rawBytes, password);
      processed = base64Encode(decrypted);
    }

    // Protobuf 解码: base64 → gzip 解压 → raw inflate → protobuf
    try {
      const compressedBytes = base64Decode(processed);
      const decompressed = await gzipDecompress(compressedBytes);
      const inflated = pako.inflate(decompressed);
      const protoType = await this._loadProto();
      return await protobufDecode(inflated, protoType);
    } catch (err) {
      throw new Error(`数据解压或解码失败: ${err.message}。如果数据未使用 protobuf 编码，请使用 decodeJson() 方法。`);
    }
  }

  /**
   * 解码 JSON 格式的 Cookie 数据（不使用 protobuf 编码的数据）。
   *
   * @param {string} jsonData - JSON 字符串
   * @returns {ICookiesMap}
   */
  decodeJson(jsonData) {
    return JSON.parse(jsonData);
  }

  /**
   * 检测数据编码类型。
   *
   * @param {string} data - 云端存储的原始数据字符串
   * @returns {'json' | 'encrypted' | 'protobuf' | 'unknown'}
   */
  static detectType(data) {
    if (!data || typeof data !== 'string') return 'unknown';

    const trimmed = data.trim();
    if (trimmed.startsWith('{')) return 'json';

    try {
      const bytes = base64Decode(trimmed);
      if (isEncrypted(bytes)) return 'encrypted';
      return 'protobuf';
    } catch {
      return 'unknown';
    }
  }

  /**
   * 重新加载 protobuf schema（切换 proto 文件后调用）。
   */
  async reloadProto() {
    this._protoType = null;
    return this._loadProto();
  }
}

/**
 * 检查 Uint8Array 是否为 AES-GCM 加密数据（检测 SYCE 魔数）。
 * @param {Uint8Array} data
 * @returns {boolean}
 */
function isEncrypted(data) {
  if (data.length < MAGIC_BYTES.length) return false;
  return data.slice(0, MAGIC_BYTES.length).every((b, i) => b === MAGIC_BYTES[i]);
}

// ─── 便捷函数 ─────────────────────────────────────────────────────────────

/**
 * 快速加密 Cookie 数据。
 * @param {ICookiesMap} cookiesMap
 * @param {string} [password] - 不传则不加密
 * @returns {Promise<string>}
 */
export async function encryptCookies(cookiesMap, password) {
  const e = new CookieEncryptor({ password });
  return e.encode(cookiesMap);
}

/**
 * 快速解密 Cookie 数据。
 * @param {string} encodedData
 * @param {string} [password]
 * @returns {Promise<ICookiesMap>}
 */
export async function decryptCookies(encodedData, password) {
  const e = new CookieEncryptor({ password });
  return e.decode(encodedData);
}

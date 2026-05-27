/**
 * Sync Your Cookie - 数据解密工具
 *
 * 用法:
 *   node tools/decrypt.mjs <encoded_data.txt>
 *   node tools/decrypt.mjs <encoded_data.txt> --password=your_password
 *   node tools/decrypt.mjs <encoded_data.txt> --password=your_password --json
 *
 * 数据来源：
 *   Cloudflare KV: https://dash.cloudflare.com/<accountId>/workers/kv/namespaces/<namespaceId>
 *   GitHub Gist:   你的 gist 文件 raw URL 内容
 *
 * 输出：解密后的 CookiesMap (JSON 格式)，包含每个域名下的 cookies 和 localStorageItems
 *
 * 依赖: pako, protobufjs (项目已有)
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import protobuf from 'protobufjs';
import pako from 'pako';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const PROTO_FILE = resolve(__dirname, '..', 'packages', 'protobuf', 'proto', 'cookie.proto');

// ─── AES-256-GCM 解密（与 encryption.ts 一致）──────────────────────────────

const MAGIC_BYTES = new Uint8Array([0x53, 0x59, 0x43, 0x45]); // "SYCE"
const SALT_LENGTH = 16;
const IV_LENGTH = 12;

async function deriveKey(password, salt) {
  const encoder = new TextEncoder();
  const passwordKey = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveKey']);
  return crypto.subtle.deriveKey(
    { name: 'PBKDF2', salt, iterations: 100000, hash: 'SHA-256' },
    passwordKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['decrypt'],
  );
}

function isEncrypted(data) {
  if (data.length < MAGIC_BYTES.length) return false;
  return data.slice(0, MAGIC_BYTES.length).every((b, i) => b === MAGIC_BYTES[i]);
}

async function decrypt(encryptedData, password) {
  let offset = 0;
  const magic = encryptedData.slice(offset, offset + MAGIC_BYTES.length);
  offset += MAGIC_BYTES.length;
  if (!magic.every((b, i) => b === MAGIC_BYTES[i])) {
    throw new Error('数据格式错误：魔数不匹配');
  }

  const version = encryptedData[offset];
  offset += 1;
  if (version !== 1) {
    throw new Error(`不支持的加密版本: ${version}`);
  }

  const salt = encryptedData.slice(offset, offset + SALT_LENGTH);
  offset += SALT_LENGTH;
  const iv = encryptedData.slice(offset, offset + IV_LENGTH);
  offset += IV_LENGTH;
  const ciphertext = encryptedData.slice(offset);

  const key = await deriveKey(password, salt);
  try {
    const decrypted = await crypto.subtle.decrypt({ name: 'AES-GCM', iv }, key, ciphertext);
    return new Uint8Array(decrypted);
  } catch {
    throw new Error('解密失败：密码错误或数据已损坏');
  }
}

// ─── Base64 编解码 ────────────────────────────────────────────────────────

function base64ToUint8Array(base64) {
  const binaryString = atob(base64.trim());
  const bytes = new Uint8Array(binaryString.length);
  for (let i = 0; i < binaryString.length; i++) {
    bytes[i] = binaryString.charCodeAt(i);
  }
  return bytes;
}

function uint8ArrayToBase64(bytes) {
  let base64 = '';
  const encodings = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  const byteLength = bytes.byteLength;
  const byteRemainder = byteLength % 3;
  const mainLength = byteLength - byteRemainder;

  for (let i = 0; i < mainLength; i += 3) {
    const chunk = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    base64 += encodings[(chunk & 16515072) >> 18] + encodings[(chunk & 258048) >> 12] +
              encodings[(chunk & 4032) >> 6] + encodings[chunk & 63];
  }
  if (byteRemainder === 1) {
    const chunk = bytes[mainLength];
    base64 += encodings[(chunk & 252) >> 2] + encodings[(chunk & 3) << 4] + '==';
  } else if (byteRemainder === 2) {
    const chunk = (bytes[mainLength] << 8) | bytes[mainLength + 1];
    base64 += encodings[(chunk & 64512) >> 10] + encodings[(chunk & 1008) >> 4] + encodings[(chunk & 15) << 2] + '=';
  }
  return base64;
}

// ─── Gzip 解压 ────────────────────────────────────────────────────────────

async function decompressGzip(compressedBytes) {
  const stream = new Blob([compressedBytes]).stream();
  const decompressedStream = stream.pipeThrough(new DecompressionStream('gzip'));
  const chunks = [];
  for await (const chunk of decompressedStream) {
    chunks.push(chunk);
  }
  const blob = new Blob(chunks);
  return new Uint8Array(await blob.arrayBuffer());
}

// ─── Protobuf 解码 ────────────────────────────────────────────────────────

async function decodeCookiesMap(buffer) {
  const root = await protobuf.load(PROTO_FILE);
  const CookiesMap = root.lookupType('CookiesMap');
  return CookiesMap.decode(buffer);
}

// ─── 主流程 ───────────────────────────────────────────────────────────────

async function main() {
  const args = process.argv.slice(2);

  if (args.length === 0 || args.includes('--help') || args.includes('-h')) {
    console.log(`
Sync Your Cookie - 数据解密工具

用法:
  node tools/decrypt.mjs <文件路径> [选项]
  node tools/decrypt.mjs -c <base64内容> [选项]

选项:
  --password=<密码>   加密密码（未加密数据不需要）
  --json              数据是 JSON 格式（未使用 protobuf 编码时）
  --output=<文件>     输出到文件（默认输出到控制台）
  -c <内容>          直接传入 base64 编码的数据内容
  --help, -h          显示帮助信息

示例:
  # 解密从 Cloudflare KV 页面复制的 protobuf 加密数据
  node tools/decrypt.mjs data.txt --password=mypassword

  # 解密未加密的 protobuf 数据
  node tools/decrypt.mjs data.txt

  # 还原 JSON 格式的数据（未使用 protobuf 编码）
  node tools/decrypt.mjs data.txt --json

  # 直接传入 base64 字符串
  node tools/decrypt.mjs -c "U3luYy..." --password=mypassword

  # 输出到文件
  node tools/decrypt.mjs data.txt --password=mypassword --output=result.json
`);
    return;
  }

  let rawContent;
  let password = '';
  let forceJson = false;
  let outputFile = '';

  for (const arg of args) {
    if (arg.startsWith('--password=')) {
      password = arg.slice('--password='.length);
    } else if (arg === '--json') {
      forceJson = true;
    } else if (arg.startsWith('--output=')) {
      outputFile = arg.slice('--output='.length);
    }
  }

  // 从命令行直接读内容
  const cIndex = args.indexOf('-c');
  if (cIndex !== -1 && cIndex + 1 < args.length) {
    rawContent = args[cIndex + 1];
  } else {
    // 从文件读
    const fileArg = args.find(a => !a.startsWith('--') && a !== '-c');
    if (fileArg && !password && !forceJson && !outputFile) {
      // 实际情况中 fileArg 是第一个非 -- 参数
    }
    const inputFile = args[0];
    if (!inputFile || inputFile.startsWith('--') || inputFile === '-c') {
      console.error('错误: 请指定输入文件或使用 -c 传入数据');
      process.exit(1);
    }
    try {
      rawContent = readFileSync(inputFile, 'utf-8').trim();
    } catch {
      console.error(`错误: 无法读取文件 "${inputFile}"`);
      process.exit(1);
    }
  }

  if (!rawContent) {
    console.error('错误: 输入数据为空');
    process.exit(1);
  }

  console.log('数据长度:', rawContent.length, '字符');

  // ─── 步骤 1: 判断格式 ──────────────────────────────────────────────────

  let processedContent = rawContent;

  // 如果是纯 JSON（以 { 开头），直接解析
  if (!forceJson && rawContent.startsWith('{')) {
    console.log('→ 检测到 JSON 格式，直接解析...');
    const result = JSON.parse(rawContent);
    output(result, outputFile);
    return;
  }

  if (forceJson) {
    console.log('→ 强制 JSON 模式，直接解析...');
    try {
      const result = JSON.parse(rawContent);
      output(result, outputFile);
    } catch {
      console.error('错误: JSON 解析失败，数据可能不是 JSON 格式');
      process.exit(1);
    }
    return;
  }

  // ─── 步骤 2: base64 解码，检测是否加密 ──────────────────────────────────

  let rawBytes;
  try {
    rawBytes = base64ToUint8Array(rawContent);
  } catch {
    console.error('错误: base64 解码失败，数据格式不正确');
    process.exit(1);
  }

  const encrypted = isEncrypted(rawBytes);
  console.log(encrypted ? '→ 检测到 AES-256-GCM 加密数据 (SYCE)' : '→ 数据未加密');

  if (encrypted) {
    if (!password) {
      console.error('\n错误: 检测到加密数据，但未提供密码。\n请使用 --password=<密码> 参数指定解密密码。');
      process.exit(1);
    }
    try {
      const decryptedBytes = await decrypt(rawBytes, password);
      // 解密后的数据是"内部 base64"编码的
      processedContent = uint8ArrayToBase64(decryptedBytes);
      console.log('✓ AES-256-GCM 解密成功');
    } catch (err) {
      console.error('解密失败:', err.message);
      process.exit(1);
    }
  }

  // ─── 步骤 3: base64 → gzip 解压 → raw inflate → protobuf 解码 ─────────

  try {
    const compressedBytes = base64ToUint8Array(processedContent);
    console.log('→ 解压 gzip...');
    const gzipDecompressed = await decompressGzip(compressedBytes);
    console.log('→ raw inflate (pako)...');
    const inflated = pako.inflate(gzipDecompressed);
    console.log('→ protobuf 解码...');
    const cookiesMap = await decodeCookiesMap(inflated);

    output(cookiesMap, outputFile);
  } catch (err) {
    console.error('解压/解码失败:', err.message);
    console.error('可能原因:');
    console.error('  1. 密码错误（如果是加密数据）');
    console.error('  2. 数据格式不支持（可能没有使用 protobuf 编码，试试 --json）');
    console.error('  3. 数据不完整或已损坏');
    process.exit(1);
  }
}

function timestampToDate(ts) {
  if (!ts) return '';
  const n = typeof ts === 'object' && ts.toNumber ? ts.toNumber() : Number(ts);
  return new Date(n).toISOString();
}

function output(cookiesMap, outputFile) {
  // 转换 Long 类型为数字
  const result = JSON.parse(JSON.stringify(cookiesMap, (key, value) => {
    if (typeof value === 'object' && value !== null && typeof value.toNumber === 'function') {
      return value.toNumber();
    }
    return value;
  }));

  // 统计信息
  let totalCookies = 0;
  let totalLocalStorage = 0;
  const domains = [];
  if (result.domainCookieMap) {
    for (const [domain, data] of Object.entries(result.domainCookieMap)) {
      const cookieCount = data.cookies?.length || 0;
      const lsCount = data.localStorageItems?.length || 0;
      totalCookies += cookieCount;
      totalLocalStorage += lsCount;
      if (cookieCount > 0 || lsCount > 0) {
        domains.push({ domain, cookieCount, lsCount });
      }
    }
  }

  const jsonOutput = JSON.stringify(result, null, 2);

  if (outputFile) {
    writeFileSync(outputFile, jsonOutput, 'utf-8');
    console.log(`\n✓ 结果已写入: ${outputFile}`);
  } else {
    console.log('\n' + '='.repeat(60));
    console.log('解密结果 (CookiesMap):');
    console.log('='.repeat(60));
    console.log(jsonOutput);
  }

  console.log('\n' + '─'.repeat(60));
  console.log('统计信息:');
  console.log(`  创建时间: ${timestampToDate(result.createTime)}`);
  console.log(`  更新时间: ${timestampToDate(result.updateTime)}`);
  console.log(`  域名总数: ${domains.length}`);
  console.log(`  Cookie 总数: ${totalCookies}`);
  console.log(`  LocalStorage 条目: ${totalLocalStorage}`);
  if (domains.length > 0) {
    console.log('\n  域名列表:');
    for (const d of domains) {
      console.log(`    ${d.domain} - ${d.cookieCount} cookies, ${d.lsCount} localStorage items`);
    }
  }
  console.log('─'.repeat(60));
}

main().catch(err => {
  console.error('未知错误:', err);
  process.exit(1);
});

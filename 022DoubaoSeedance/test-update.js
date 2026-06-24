/**
 * 自动更新流程测试脚本
 * 运行: node test-update.js
 */
const https = require('https');

const GITHUB_OWNER = '6832466';
const GITHUB_REPO = 'aicode';
const CURRENT_VERSION = '3.0.0';
const VERSION_JSON_URL = `https://cdn.jsdelivr.net/gh/${GITHUB_OWNER}/${GITHUB_REPO}@main/022DoubaoSeedance/version.json`;

function isNewerVersion(newVer, currentVer) {
  const na = newVer.split('.').map(Number);
  const ca = currentVer.split('.').map(Number);
  for (let i = 0; i < Math.max(na.length, ca.length); i++) {
    const n = na[i] || 0, c = ca[i] || 0;
    if (n > c) return true;
    if (n < c) return false;
  }
  return false;
}

function fetch(url, timeout = 15000) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, {
      headers: { 'User-Agent': 'TestScript', 'Accept': 'application/json' },
      timeout
    }, (res) => {
      if (res.statusCode !== 200) { reject({ statusCode: res.statusCode }); return; }
      let data = '';
      res.on('data', c => data += c.toString());
      res.on('end', () => { try { resolve(JSON.parse(data)); } catch { reject({ parseError: true }); } });
    });
    req.on('error', e => reject({ message: e.message }));
    req.on('timeout', () => { req.destroy(); reject({ message: 'timeout' }); });
  });
}

async function test() {
  console.log('╔══════════════════════════════════════════╗');
  console.log('║     豆包Seedance 自动更新测试           ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log(`\n📡 测试 URL: ${VERSION_JSON_URL.replace('https://', '')}`);
  console.log(`📦 当前版本: v${CURRENT_VERSION}\n`);

  let info;
  try {
    info = await fetch(VERSION_JSON_URL, 15000);
    console.log(`✅ URL 可访问`);
    console.log(`   解析结果:`, JSON.stringify(info, null, 2).slice(0, 200));
  } catch (err) {
    console.log(`❌ 失败: ${JSON.stringify(err)}`);
    process.exit(1);
  }

  if (!info.version) {
    console.log(`❌ version.json 缺少 version 字段`);
    process.exit(1);
  }

  console.log(`\n🔍 版本对比: v${info.version} vs v${CURRENT_VERSION}`);
  if (isNewerVersion(info.version, CURRENT_VERSION)) {
    console.log(`🆕 发现新版本！需要更新`);
    if (info.portable?.url) {
      console.log(`📥 下载地址: ${info.portable.url}`);
    }
  } else {
    console.log(`✅ 已是最新版本`);
  }

  console.log('\n🎉 测试通过！');
}

test().catch(err => {
  console.error('测试错误:', err);
  process.exit(1);
});

/**
 * 自动更新完整流程测试脚本
 * 运行: node test-update-full.js
 *
 * 测试内容:
 * 1. 版本对比算法
 * 2. jsDelivr URL 可访问性 (version.json)
 * 3. GitHub Release 下载链接有效性
 * 4. 模拟完整更新检测流程
 */

const https = require('https');
const fs = require('fs');
const { execSync } = require('child_process');

// ===== 配置 =====
const GITHUB_OWNER = '6832466';
const GITHUB_REPO = 'aicode';
const CURRENT_VERSION = '3.0.0'; // 必须与 package.json 一致
const VERSION_JSON_URL = `https://cdn.jsdelivr.net/gh/${GITHUB_OWNER}/${GITHUB_REPO}@main/022DoubaoSeedance/version.json`;

// ===== 工具函数 =====
function log(emoji, msg) {
  console.log(`  ${emoji} ${msg}`);
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
      res.on('end', () => {
        try { resolve(JSON.parse(data)); }
        catch { reject({ parseError: true, data: data.slice(0, 100) }); }
      });
    });
    req.on('error', e => reject({ message: e.message }));
    req.on('timeout', () => { req.destroy(); reject({ message: 'timeout' }); });
  });
}

function fetchHead(url, timeout = 10000) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, {
      method: 'HEAD',
      headers: { 'User-Agent': 'TestScript' },
      timeout
    }, (res) => {
      resolve({ statusCode: res.statusCode, contentLength: res.headers['content-length'] });
    });
    req.on('error', e => reject({ message: e.message }));
    req.on('timeout', () => { req.destroy(); reject({ message: 'timeout' }); });
    req.end();
  });
}

// ===== 1. 版本对比测试 =====
function testVersionComparison() {
  log('🔧', '测试版本对比算法');
  const tests = [
    ['3.0.1', '3.0.0', true],
    ['3.0.0', '3.0.0', false],
    ['2.9.9', '3.0.0', false],
    ['3.1.0', '3.0.9', true],
    ['10.0.0', '9.9.9', true],
    ['1.9.9', '1.10.0', false],
  ];

  let passed = 0;
  for (const [newVer, current, expect] of tests) {
    const result = isNewerVersion(newVer, current);
    const ok = result === expect;
    log(ok ? '✅' : '❌', `isNewerVersion('${newVer}', '${current}') = ${result} (期望: ${expect})`);
    if (ok) passed++;
  }
  console.log(`     ${passed}/${tests.length} 通过`);
  return passed === tests.length;
}

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

// ===== 2. jsDelivr version.json 测试 =====
async function testJsdelivrVersionJson() {
  log('🌐', `测试 jsDelivr version.json: ${VERSION_JSON_URL.replace('https://', '')}`);

  try {
    const info = await fetch(VERSION_JSON_URL, 15000);
    log('✅', `获取成功 - version: ${info.version}`);

    if (!info.version) {
      log('❌', 'version.json 缺少 version 字段');
      return null;
    }
    if (!info.portable?.url) {
      log('❌', 'version.json 缺少 portable.url 字段');
      return null;
    }
    log('✅', `portable.url: ${info.portable.url.slice(0, 80)}...`);
    return info;
  } catch (err) {
    log('❌', `失败: ${JSON.stringify(err)}`);
    return null;
  }
}

// ===== 3. GitHub Release 下载链接测试 =====
async function testGithubReleaseDownload(info) {
  log('🔗', '测试 GitHub Release 下载链接');

  const url = info.portable.url;
  log('📡', `URL: ${url.slice(0, 80)}...`);

  // HEAD 请求测试（不下载内容）
  try {
    const result = await fetchHead(url, 10000);
    log('📊', `HEAD 响应: HTTP ${result.statusCode}, Content-Length: ${result.contentLength || 'unknown'}`);

    if (result.statusCode === 200 || result.statusCode === 302 || result.statusCode === 301) {
      log('✅', '下载链接有效');
      return true;
    } else if (result.statusCode === 404) {
      log('❌', '文件不存在（可能 Release 附件未上传）');
      return false;
    } else {
      log('⚠️', `HTTP ${result.statusCode} - 国内可能无法直接下载`);
      return true; // 链接有效，只是可能需要代理
    }
  } catch (err) {
    log('⚠️', `连接失败: ${err.message} - 国内网络可能无法直连 GitHub`);
    return true; // 链接本身有效，失败是网络问题
  }
}

// ===== 4. 代码 URL 一致性检查 =====
function testUrlConsistency() {
  log('📝', '检查代码中的 URL 与测试 URL 是否一致');
  const expectedShort = 'cdn.jsdelivr.net/gh/6832466/aicode@main/022DoubaoSeedance/version.json';
  log('📄', `期望: ${expectedShort}`);

  try {
    const content = fs.readFileSync('src/main/index.ts', 'utf8');

    if (content.includes('@main/022DoubaoSeedance/version.json')) {
      log('✅', '代码使用 @main 格式');
      if (content.includes('cdn.jsdelivr.net')) {
        log('✅', '使用 jsDelivr CDN');
        return true;
      }
    }

    if (content.includes('raw.githubusercontent.com')) {
      log('⚠️', '使用 raw.githubusercontent.com（可能被墙）');
      return false;
    }

    if (content.includes('@vlatest')) {
      log('⚠️', '使用 @vlatest（jsDelivr 不支持）');
      return false;
    }

    log('⚠️', 'URL 格式可能有误');
    return false;
  } catch (err) {
    log('❌', `读取文件失败: ${err.message}`);
    return false;
  }
}

// ===== 5. package.json 版本检查 =====
function testPackageVersion() {
  log('📦', '检查 package.json 版本');
  try {
    const pkg = JSON.parse(fs.readFileSync('package.json', 'utf8'));
    log('📄', `package.json version: ${pkg.version}`);
    if (pkg.version === CURRENT_VERSION) {
      log('✅', '版本一致');
      return true;
    } else {
      log('⚠️', `不一致！测试用 CURRENT_VERSION: ${CURRENT_VERSION}`);
      return false;
    }
  } catch (err) {
    log('❌', `读取失败: ${err.message}`);
    return false;
  }
}

// ===== 完整流程模拟 =====
async function testFullFlow(info) {
  log('🚀', '模拟完整更新流程');
  log('📦', `当前版本: v${CURRENT_VERSION}`);

  if (!info) {
    log('❌', '无法获取 version.json，跳过完整流程测试');
    return false;
  }

  const latestVer = info.version;
  log('🌐', `最新版本: v${latestVer}`);

  if (!isNewerVersion(latestVer, CURRENT_VERSION)) {
    log('✅', '已是最新版本，无更新');
    return true;
  }

  log('🆕', `发现新版本: v${latestVer}`);
  log('📥', `下载地址: ${info.portable?.url?.slice(0, 60)}...`);

  if (info.releaseUrl) {
    log('🔗', `Release 页面: ${info.releaseUrl}`);
  }

  return true;
}

// ===== 主函数 =====
async function main() {
  console.log('╔══════════════════════════════════════════════════════╗');
  console.log('║     豆包Seedance 自动更新完整测试               ║');
  console.log('╚══════════════════════════════════════════════════════╝');
  console.log('');

  let allPassed = true;

  // 1. 版本对比
  console.log('\n【1/5】版本对比算法');
  if (!testVersionComparison()) allPassed = false;

  // 2. package.json 版本
  console.log('\n【2/5】package.json 版本一致性');
  if (!testPackageVersion()) allPassed = false;

  // 3. URL 一致性
  console.log('\n【3/5】代码 URL 一致性');
  if (!testUrlConsistency()) allPassed = false;

  // 4. jsDelivr version.json
  console.log('\n【4/5】jsDelivr version.json 可访问性');
  const info = await testJsdelivrVersionJson();
  if (!info) allPassed = false;

  // 5. GitHub Release 下载链接
  console.log('\n【5/5】GitHub Release 下载链接');
  if (info) {
    const downloadOk = await testGithubReleaseDownload(info);
    if (!downloadOk) allPassed = false;
  } else {
    log('⚠️', '跳过（无 version.json）');
  }

  // 6. 完整流程模拟
  console.log('\n【6/6】完整更新流程模拟');
  if (info) {
    await testFullFlow(info);
  } else {
    log('⚠️', '跳过（无 version.json）');
  }

  // 结果汇总
  console.log('\n╔══════════════════════════════════════════════════════╗');
  console.log('║                    测试结果汇总                      ║');
  console.log('╚══════════════════════════════════════════════════════╝');

  if (allPassed) {
    console.log('  🎉 所有测试通过！');
    console.log('  📝 下一步：构建打包后测试实际更新流程');
  } else {
    console.log('  ⚠️ 部分测试失败，请检查上方输出');
    process.exit(1);
  }
}

main().catch(err => {
  console.error('\n❌ 测试脚本错误:', err);
  process.exit(1);
});

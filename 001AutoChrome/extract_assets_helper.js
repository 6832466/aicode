/**
 * 浏览器控制台助手 - 提取 RunwayML 中已添加的人物引用 assetId
 *
 * 使用方法:
 * 1. 在 RunwayML 页面中，添加你需要的人物引用（点击 "Reference" 按钮，双击人物图片）
 * 2. 打开 Chrome DevTools Console (F12 → Console)
 * 3. 复制粘贴此脚本并回车运行
 * 4. 复制输出的 JSON 结果，添加到 character_assets.json 中
 */

(async function extractCharacterAssets() {
  const results = {};

  // 方法1: 从页面上已添加的 Reference 按钮中提取
  const allButtons = document.querySelectorAll('button');

  for (const btn of allButtons) {
    const text = btn.textContent.trim();
    // 跳过太长的按钮文本（不是人名）
    if (text.length > 20) continue;

    // 遍历 React fiber 树查找 reference 数据
    for (const key of Object.keys(btn)) {
      if (!key.startsWith('__reactFiber')) continue;

      let fiber = btn[key];
      for (let i = 0; i < 50 && fiber; i++) {
        try {
          const props = fiber.memoizedProps;
          if (props) {
            // 检查 reference prop (对象或JSON字符串格式)
            const refVal = props.reference || props.assetReference;
            if (refVal) {
              // 对象格式: { assetId, tag, url, ... }
              if (typeof refVal === 'object' && refVal.assetId) {
                const tag = refVal.tag || refVal.name || refVal.id;
                if (tag && !results[tag]) {
                  results[tag] = { assetId: refVal.assetId, url: (refVal.url || '').substring(0, 200) };
                }
              }
              // JSON字符串格式
              if (typeof refVal === 'string' && refVal.includes('assetId')) {
                try {
                  const parsed = JSON.parse(refVal);
                  if (parsed.assetId && parsed.tag) {
                    if (!results[parsed.tag]) {
                      results[parsed.tag] = { assetId: parsed.assetId, url: (parsed.url || '').substring(0, 200) };
                    }
                  }
                } catch(e) {}
              }
            }
            // 同时也检查其他可能包含 assetId 的 prop
            for (const pk of Object.keys(props)) {
              const pv = props[pk];
              if (typeof pv === 'object' && pv && pv.assetId && pv.tag && pk !== 'reference' && pk !== 'assetReference') {
                if (!results[pv.tag]) {
                  results[pv.tag] = { assetId: pv.assetId, url: (pv.url || '').substring(0, 200) };
                }
              }
            }
          }
        } catch(e) {}
        fiber = fiber.return;
      }
    }
  }

  // 方法2: 如果你已经点击了 Generate，可以从网络请求中获取
  // 打开 Network 面板，找到 POST /v1/generations 请求
  // 在 Request Payload 中查看 settings.referenceImages

  if (Object.keys(results).length === 0) {
    console.log('未找到已添加的人物引用。');
    console.log('请先在页面上添加人物引用（点击 Reference 按钮 → 搜索 → 双击人物图片）');
    console.log('或者查看 Network 面板中的 POST /v1/generations 请求');
    console.log('\n提示: 运行以下代码可以拦截下一次 Generation 请求:');
    console.log(`
// 拦截网络请求
const origFetch = window.fetch;
window.fetch = async (...args) => {
  const resp = await origFetch(...args);
  if (args[0].includes('/generations') && args[1]?.method === 'POST') {
    const body = JSON.parse(args[1].body);
    console.log('Reference Images:', JSON.stringify(body.settings.referenceImages, null, 2));
  }
  return resp;
};
    `);
  } else {
    console.log('找到以下人物 Asset 映射:');
    console.log(JSON.stringify(results, null, 2));
    console.log('\n复制上面的 JSON 添加到 character_assets.json 文件中');
  }

  return results;
})();

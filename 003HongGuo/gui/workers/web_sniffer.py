"""Web 嗅探器 — QWebChannel 桥接 + 持久化 Profile + JS 注入脚本"""
import json
import logging
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineScript

logger = logging.getLogger("hongguo")

PROJECT_ROOT = Path(__file__).parent.parent.parent
WEB_PROFILE_PATH = str(PROJECT_ROOT / ".webengine_profile")

MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 "
    "Mobile/15E148 Safari/604.1"
)

# ==================== 手机模拟 JS ====================
# 注入时机: DocumentCreation (早于任何页面脚本)
# 覆盖浏览器特征检测, 避免"打开 App"类提示

MOBILE_EMULATION_JS = r"""
(function() {
    // -- navigator 属性覆盖 --
    var _navigator = navigator;
    var props = {
        platform: { value: 'iPhone', configurable: false },
        maxTouchPoints: { value: 5, configurable: false },
        msMaxTouchPoints: { value: 5, configurable: false },
        hardwareConcurrency: { value: 6, configurable: false },
        deviceMemory: { value: 4, configurable: false },
    };
    for (var k in props) {
        try {
            Object.defineProperty(_navigator, k, props[k]);
        } catch(e) {}
    }
    // 部分浏览器 navigator.platform 不可写, 备用方案
    try {
        Object.defineProperty(Navigator.prototype, 'platform', { get: function() { return 'iPhone'; } });
    } catch(e) {}

    // -- window 触控属性 --
    var touchProps = ['ontouchstart', 'ontouchmove', 'ontouchend', 'ontouchcancel'];
    for (var i = 0; i < touchProps.length; i++) {
        try {
            window.__defineGetter__(touchProps[i], function() { return null; });
        } catch(e) {}
    }
    // document 触控
    try { document.__defineGetter__('ontouchstart', function() { return null; }); } catch(e) {}

    // -- Screen 尺寸模拟 (iPhone 14 Pro 逻辑分辨率) --
    var _screen = screen;
    try {
        Object.defineProperty(Screen.prototype, 'width',  { get: function() { return 390; } });
        Object.defineProperty(Screen.prototype, 'height', { get: function() { return 844; } });
        Object.defineProperty(Screen.prototype, 'availWidth',  { get: function() { return 390; } });
        Object.defineProperty(Screen.prototype, 'availHeight', { get: function() { return 844; } });
        Object.defineProperty(Screen.prototype, 'colorDepth',  { get: function() { return 24; } });
        Object.defineProperty(Screen.prototype, 'pixelDepth',  { get: function() { return 24; } });
    } catch(e) {}

    // -- TouchEvent 构造函数存在性 --
    if (typeof TouchEvent === 'undefined') {
        try {
            window.TouchEvent = function(type, init) {
                var e = document.createEvent('TouchEvent');
                if (e.initTouchEvent) {
                    e.initTouchEvent(type, init.bubbles, init.cancelable,
                        init.view, init.detail, init.ctrlKey, init.altKey,
                        init.shiftKey, init.metaKey,
                        init.touches, init.targetTouches, init.changedTouches,
                        init.scale, init.rotation);
                }
                return e;
            };
        } catch(e) {}
    }

    // -- CSS media query 覆盖: pointer:coarse, hover:none --
    var _origMatchMedia = window.matchMedia;
    window.matchMedia = function(query) {
        if (typeof query === 'string') {
            if (query.indexOf('pointer') !== -1 && query.indexOf('coarse') !== -1) {
                return { matches: true, media: query, addListener: function(){}, removeListener: function(){}, addEventListener: function(){}, removeEventListener: function(){} };
            }
            if (query.indexOf('hover') !== -1 && query.indexOf('none') !== -1) {
                return { matches: true, media: query, addListener: function(){}, removeListener: function(){}, addEventListener: function(){}, removeEventListener: function(){} };
            }
            if (query.indexOf('any-hover') !== -1 && query.indexOf('none') !== -1) {
                return { matches: true, media: query, addListener: function(){}, removeListener: function(){}, addEventListener: function(){}, removeEventListener: function(){} };
            }
            if (query.indexOf('any-pointer') !== -1 && query.indexOf('coarse') !== -1) {
                return { matches: true, media: query, addListener: function(){}, removeListener: function(){}, addEventListener: function(){}, removeEventListener: function(){} };
            }
        }
        return _origMatchMedia.call(window, query);
    };

    // -- navigator.standalone (伪装 iOS PWA, 隐藏"打开App"提示) --
    try {
        Object.defineProperty(_navigator, 'standalone', { get: function() { return true; } });
    } catch(e) {
        try { Object.defineProperty(Navigator.prototype, 'standalone', { get: function() { return true; } }); } catch(e2) {}
    }

    // -- CSS: 隐藏"打开App"/"前往观看"类推广元素 --
    function injectAppHideCSS() {
        var style = document.createElement('style');
        style.id = '__mobile_hide_app_prompts__';
        style.textContent = [
            '/* 通用: 隐藏所有包含"打开"/"App"/"前往"的浮层和按钮 */',
            '[class*="open-app"], [class*="openApp"], [class*="open_app"],',
            '[class*="app-banner"], [class*="appBanner"], [class*="app_banner"],',
            '[class*="app-download"], [class*="appDownload"], [class*="app_download"],',
            '[class*="download-bar"], [class*="downloadBar"],',
            '[class*="go-app"], [class*="goApp"],',
            '[class*="launch-app"], [class*="launchApp"],',
            '[class*="app-launcher"], [class*="appLauncher"],',
            '[class*="open-in-app"], [class*="openInApp"],',
            '[class*="guide-bar"], [class*="guideBar"],',
            '[id*="open-app"], [id*="openApp"],',
            '[id*="app-banner"], [id*="appBanner"],',
            '[id*="app-download"], [id*="appDownload"],',
            '{ display: none !important; visibility: hidden !important; pointer-events: none !important; }',
            '/* 固定底部/顶部的推广条 */',
            'div[style*=\"fixed\"][style*=\"bottom\"]:has(a[href*=\"app\"]),',
            'div[style*=\"fixed\"]:has(button):not(:has(iframe)) { display: none !important; }',
        ].join('\n');
        document.head.appendChild(style);
    }

    // -- 注入 viewport meta (DOM 就绪后) --
    function injectViewport() {
        var meta = document.querySelector('meta[name=\"viewport\"]');
        if (!meta) {
            meta = document.createElement('meta');
            meta.name = 'viewport';
            document.head.appendChild(meta);
        }
        meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover';
    }

    function onDOMReady() {
        injectViewport();
        injectAppHideCSS();
        startTextFilter();
    }

    // -- MutationObserver: 移除包含"打开App""前往观看"等文本的动态元素 --
    function startTextFilter() {
        var keywords = ['打开App', '打开 APP', '前往剧集', '前往观看', '打开剧集', '下载App', '下载 APP',
                        '打开客户端', 'App观看', 'APP观看', 'app观看', '打开app'];
        function shouldRemove(el) {
            // 跳过已处理的和核心元素
            if (el.dataset && el.dataset.__filtered) return false;
            if (el.tagName === 'HTML' || el.tagName === 'BODY' || el.tagName === 'HEAD') return false;
            if (el.tagName === 'SCRIPT' || el.tagName === 'STYLE' || el.tagName === 'LINK') return false;
            if (el.id === '__mobile_hide_app_prompts__') return false;

            var text = (el.textContent || '').substring(0, 80);
            for (var i = 0; i < keywords.length; i++) {
                if (text.indexOf(keywords[i]) !== -1) return true;
            }
            return false;
        }
        function scanAndRemove(root) {
            // 广度优先扫描, 只处理直接子元素中的小节点
            var walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT, null, false);
            var toRemove = [];
            var node;
            while (node = walker.nextNode()) {
                // 只检查叶子附近的节点 (按钮/span/a/div 等)
                var tag = node.tagName;
                if (tag === 'BUTTON' || tag === 'A' || tag === 'SPAN' || tag === 'DIV') {
                    if (shouldRemove(node)) {
                        var rect = node.getBoundingClientRect();
                        // 只移除可见且尺寸适中的元素 (避免误删大面积内容)
                        if (rect.width > 0 && rect.width < 600 && rect.height > 10 && rect.height < 200) {
                            toRemove.push(node);
                        }
                    }
                }
            }
            for (var i = 0; i < toRemove.length; i++) {
                try {
                    toRemove[i].style.display = 'none';
                    toRemove[i].style.visibility = 'hidden';
                    toRemove[i].dataset.__filtered = '1';
                } catch(e) {}
            }
        }
        scanAndRemove(document.body);
        // 监听后续 DOM 变化
        var observer = new MutationObserver(function(mutations) {
            for (var i = 0; i < mutations.length; i++) {
                var m = mutations[i];
                for (var j = 0; j < m.addedNodes.length; j++) {
                    var node = m.addedNodes[j];
                    if (node.nodeType === 1) {
                        // 延迟扫描, 等文本内容填充
                        setTimeout(function(n) { scanAndRemove(n); }, 300, node);
                    }
                }
            }
        });
        if (document.body) {
            observer.observe(document.body, { childList: true, subtree: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', onDOMReady);
    } else {
        onDOMReady();
    }
})();
"""

# ==================== QWebChannel 桥接 JS ====================
# 注入时机: loadFinished 后 (依赖 qwebchannel.js)
# 监听 window._ROUTER_DATA 并通过 bridge 发送给 Python

INJECT_SCRIPT = r"""
new QWebChannel(qt.webChannelTransport, function(channel) {
    window.bridge = channel.objects.bridge;

    function sendData() {
        if (window._ROUTER_DATA) {
            var data = JSON.stringify(window._ROUTER_DATA);
            bridge.send_router_data(data, window.location.href);
            return true;
        }
        return false;
    }

    if (!sendData()) {
        setTimeout(sendData, 1500);
    }

    var origPush = history.pushState;
    var origReplace = history.replaceState;
    function onNav() { setTimeout(sendData, 800); }
    history.pushState = function() { origPush.apply(this, arguments); onNav(); };
    history.replaceState = function() { origReplace.apply(this, arguments); onNav(); };
    window.addEventListener('popstate', function() { setTimeout(sendData, 1200); });
});
"""


class WebSnifferBridge(QObject):
    """通过 QWebChannel 暴露给 JS 的桥接对象"""
    router_data_received = Signal(str, str)  # json_str, current_page_url

    @Slot(str, str)
    def send_router_data(self, json_str: str, current_url: str):
        """JS 调用: bridge.send_router_data(JSON.stringify(window._ROUTER_DATA), location.href)"""
        self.router_data_received.emit(json_str, current_url)


def create_persistent_profile() -> QWebEngineProfile:
    """创建持久化 WebEngine Profile (保存 cookies / 登录状态)"""
    profile = QWebEngineProfile("hongguo_browser")
    profile.setPersistentStoragePath(WEB_PROFILE_PATH)
    profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
    profile.setHttpUserAgent(MOBILE_UA)

    # 注入手机模拟脚本 (DocumentCreation 阶段, 早于任何页面 JS)
    script = QWebEngineScript()
    script.setName("mobile_emulation")
    script.setSourceCode(MOBILE_EMULATION_JS)
    script.setInjectionPoint(QWebEngineScript.DocumentCreation)
    script.setWorldId(QWebEngineScript.MainWorld)
    script.setRunsOnSubFrames(True)
    profile.scripts().insert(script)

    logger.info(f"WebEngine profile: {WEB_PROFILE_PATH}")
    return profile


def setup_web_channel(page, bridge: WebSnifferBridge):
    """给页面设置 QWebChannel, 注册 bridge 对象"""
    from PySide6.QtWebChannel import QWebChannel
    channel = QWebChannel(page)
    channel.registerObject("bridge", bridge)
    page.setWebChannel(channel)
    return channel

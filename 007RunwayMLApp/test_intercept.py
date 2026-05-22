"""
Intercept ALL network requests from RunwayML web app to capture
the exact POST /v1/generations payload format.
"""
import sys
import json
import os
from pathlib import Path

from PySide6.QtCore import QUrl, QTimer, QEventLoop, QByteArray
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEngineProfile, QWebEngineUrlRequestInterceptor,
    QWebEngineUrlRequestInfo,
)
from PySide6.QtWidgets import QApplication

CAPTURED = []
TOOLS_URL = "https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate?tool=video&mode=tools"


class RequestInterceptor(QWebEngineUrlRequestInterceptor):
    """Capture all API requests and responses."""
    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        url = info.requestUrl().toString()
        method = info.requestMethod().encode()

        # Only log API calls
        if "api.runwayml.com" not in url:
            return

        entry = {
            "url": url,
            "method": method.decode() if isinstance(method, bytes) else method,
            "headers": {},
        }

        # Capture headers from QWebEngineUrlRequestInfo
        # headers() returns QByteArray pairs
        # Actually QWebEngineUrlRequestInfo doesn't expose headers easily
        # We'll use JavaScript interception instead

        if "/v1/generations" in url or "/v1/tasks" in url:
            CAPTURED.append(entry)
            print(f"\n>>> INTERCEPTED: {method} {url}")


# JS to monitor all fetch/XHR calls
monitor_js = r"""
(function() {
    const captured = [];

    // Hook fetch
    const origFetch = window.fetch;
    window.fetch = async function(...args) {
        const [url, options = {}] = args;
        const start = Date.now();

        let reqBody = null;
        if (options.body) {
            try { reqBody = JSON.parse(options.body); } catch(e) { reqBody = options.body; }
        }

        try {
            const resp = await origFetch(...args);
            const clone = resp.clone();
            let respBody = null;
            try {
                respBody = await clone.text();
                if (respBody.length < 500) {
                    try { respBody = JSON.parse(respBody); } catch(e) {}
                } else {
                    respBody = '(truncated ' + respBody.length + ' chars)';
                }
            } catch(e) { respBody = '(error reading body)'; }

            if (url.includes('api.runwayml.com')) {
                captured.push({
                    type: 'fetch',
                    method: options.method || 'GET',
                    url: typeof url === 'string' ? url : url.toString(),
                    reqBody: reqBody,
                    respStatus: resp.status,
                    respBody: respBody,
                    time: Date.now() - start
                });
                console.log('FETCH:', options.method || 'GET', url, resp.status);
            }

            return resp;
        } catch(e) {
            if (url.includes('api.runwayml.com')) {
                captured.push({
                    type: 'fetch',
                    method: options.method || 'GET',
                    url: typeof url === 'string' ? url : url.toString(),
                    reqBody: reqBody,
                    error: e.message,
                    time: Date.now() - start
                });
            }
            throw e;
        }
    };

    // Hook XMLHttpRequest
    const OrigXHR = window.XMLHttpRequest;
    window.XMLHttpRequest = function() {
        const xhr = new OrigXHR();
        let _url, _method, _body;

        const origOpen = xhr.open;
        xhr.open = function(method, url, ...rest) {
            _url = url;
            _method = method;
            return origOpen.apply(this, [method, url, ...rest]);
        };

        const origSend = xhr.send;
        xhr.send = function(body) {
            _body = body;
            return origSend.apply(this, [body]);
        };

        xhr.addEventListener('load', function() {
            if (typeof _url === 'string' && _url.includes('api.runwayml.com')) {
                let respBody = null;
                try {
                    respBody = xhr.responseText;
                    if (respBody && respBody.length < 500) {
                        try { respBody = JSON.parse(respBody); } catch(e) {}
                    } else if (respBody) {
                        respBody = '(truncated ' + respBody.length + ' chars)';
                    }
                } catch(e) {}

                captured.push({
                    type: 'xhr',
                    method: _method,
                    url: _url,
                    reqBody: _body,
                    respStatus: xhr.status,
                    respBody: respBody,
                });
                console.log('XHR:', _method, _url, xhr.status);
            }
        });

        return xhr;
    };

    // Expose captured data
    window.__NETWORK_CAPTURED = captured;

    // Add button to dump captures
    const btn = document.createElement('button');
    btn.textContent = 'Dump API Captures';
    btn.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;padding:8px 16px;background:red;color:white;border:none;border-radius:4px;cursor:pointer;font-size:14px;';
    btn.onclick = function() {
        document.title = 'NETCAP:' + JSON.stringify(captured.slice(0, 20));
    };
    document.body.appendChild(btn);

    console.log('Network monitor installed. Captured requests will show in page title via red button.');
})();
"""

# JS to check page state
check_js = r"""
(async () => {
    let results = [];

    // 1. Token check
    let token = null;
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        const v = localStorage.getItem(k);
        if (v && v.startsWith('eyJ')) { token = v; break; }
    }
    results.push('TOKEN:' + (token ? token.substring(0, 30) + '...' : 'NONE'));

    // 2. Page content
    const bodyText = document.body?.innerText || '';
    results.push('LOGIN_SCREEN:' + (bodyText.includes('Log in') || bodyText.includes('Sign in')));
    results.push('HAS_GENERATE_BTN:' + bodyText.includes('Generate'));

    // 3. All text visible
    const snippets = bodyText.substring(0, 500).replace(/\s+/g, ' ').trim();
    results.push('PAGE_TEXT:' + snippets);

    document.title = 'STATE:' + results.join(' || ');
})();
"""

app = QApplication(sys.argv)

# Use persistent profile so login sticks
data_dir = Path.home() / ".runwayml_test_profile"
data_dir.mkdir(exist_ok=True)
profile = QWebEngineProfile("runwayml_test", app)
profile.setPersistentStoragePath(str(data_dir))
profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.DiskHttpCache)
profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies)

# Install network monitor after page loads
view = QWebEngineView()
view.resize(1400, 900)
view.setWindowTitle("RunwayML — Log in and click Generate to capture API calls")
view.show()


def on_title_changed(title):
    if title.startswith("NETCAP:"):
        print("\n" + "=" * 80)
        print("NETWORK CAPTURES:")
        print("=" * 80)
        try:
            data = json.loads(title[7:])
            for i, entry in enumerate(data):
                print(f"\n--- Capture {i+1}: {entry.get('type', '?')} {entry.get('method', '?')} {entry.get('url', '?')}")
                if entry.get('reqBody'):
                    print(f"    Request Body: {json.dumps(entry['reqBody'], indent=2, ensure_ascii=False)[:2000]}")
                print(f"    Status: {entry.get('respStatus', '?')}")
                if entry.get('respBody'):
                    print(f"    Response: {json.dumps(entry['respBody'], indent=2, ensure_ascii=False) if isinstance(entry['respBody'], dict) else str(entry['respBody'])[:500]}")
                if entry.get('error'):
                    print(f"    Error: {entry['error']}")
        except Exception as e:
            print(f"Parse error: {e}")
            print(title[7:500])
        print("\n" + "=" * 80)

    elif title.startswith("STATE:"):
        print("\n--- Page State ---")
        for part in title[6:].split(' || '):
            print(f"  {part}")
        print("---")


def on_load_finished(ok):
    if ok:
        print("\nPage loaded. Installing network monitor in 3s...")
        QTimer.singleShot(3000, lambda: view.page().runJavaScript(monitor_js))
        QTimer.singleShot(5000, lambda: view.page().runJavaScript(check_js))
        print("\n=== INSTRUCTIONS ===")
        print("1. Log in to RunwayML (if not already logged in)")
        print("2. Navigate to the Generate page")
        print("3. Enter a prompt and click Generate")
        print("4. Click the red 'Dump API Captures' button in top-right")
        print("5. The captured API calls will appear in this console")
        print("====================\n")
    else:
        print("Page load failed!")


view.loadFinished.connect(on_load_finished)
view.titleChanged.connect(on_title_changed)
view.load(QUrl(TOOLS_URL))

print("Opening RunwayML in embedded browser...")
print("Profile stored at:", data_dir)
loop = QEventLoop()
QTimer.singleShot(120000, loop.quit)  # 2 min timeout
loop.exec()

view.close()
app.quit()

"""
Try to programmatically submit a generation through the RunwayML web UI.
"""
import sys
import json
from pathlib import Path

from PySide6.QtCore import QUrl, QTimer, QEventLoop
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineProfile
from PySide6.QtWidgets import QApplication

TOOLS_URL = "https://app.runwayml.com/video-tools/teams/LeleRpa/ai-tools/generate?tool=video&mode=tools"

# JS to interact with the page UI
ui_js = r"""
(async () => {
    let results = [];

    // 1. Check login state
    let token = null;
    for (let i = 0; i < localStorage.length; i++) {
        const k = localStorage.key(i);
        const v = localStorage.getItem(k);
        if (v && v.startsWith('eyJ')) { token = v; break; }
    }
    results.push('AUTH:' + (token ? 'LOGGED_IN' : 'NOT_LOGGED_IN'));

    // 2. Check page content
    const bodyText = document.body?.innerText || '';
    results.push('HAS_GENERATE:' + bodyText.includes('Generate'));
    results.push('HAS_LOGIN:' + (bodyText.includes('Log in') || bodyText.includes('Sign in')));

    // 3. Look for model selection (Seedance 2.0)
    const allText = bodyText.substring(0, 2000);
    results.push('HAS_SEEDANCE:' + (allText.includes('Seedance') || allText.includes('seedance')));

    // 4. Find text input for prompt
    // Try multiple selectors
    const selectors = [
        'textarea',
        '[contenteditable="true"]',
        'input[type="text"]',
        'input:not([type])',
        '[data-testid]',
        '[role="textbox"]',
    ];
    let inputInfo = [];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        if (els.length > 0) {
            inputInfo.push(sel + ':' + els.length);
        }
    }
    results.push('INPUTS:' + inputInfo.join(','));

    // 5. Find buttons
    const buttons = document.querySelectorAll('button');
    let btnInfo = [];
    for (const b of buttons) {
        const text = (b.textContent || '').trim();
        if (text && text.length < 30) {
            btnInfo.push(text);
        }
    }
    results.push('BUTTONS:' + btnInfo.slice(0, 15).join(' | '));

    // 6. Try to click Generate if found
    if (token && !bodyText.includes('Log in')) {
        for (const b of buttons) {
            const text = (b.textContent || '').trim().toLowerCase();
            if (text.includes('generate') || text.includes('生成')) {
                results.push('CLICKING:' + text);
                b.click();
                break;
            }
        }
    }

    document.title = 'UI_R:' + results.join('||');
})();
"""

app = QApplication(sys.argv)
profile = QWebEngineProfile.defaultProfile()
view = QWebEngineView()
view.resize(1400, 900)
view.show()

def on_title_changed(title):
    if title.startswith("UI_R:"):
        print("\n=== PAGE ANALYSIS ===")
        for part in title[4:].split('||'):
            print(f"  {part}")

def on_load_finished(ok):
    if ok:
        print("Page loaded. Analyzing UI in 5s...")
        QTimer.singleShot(5000, lambda: view.page().runJavaScript(ui_js))
    else:
        print("Page load failed!")

view.loadFinished.connect(on_load_finished)
view.titleChanged.connect(on_title_changed)
view.load(QUrl(TOOLS_URL))

print("Analyzing RunwayML page UI...")
loop = QEventLoop()
QTimer.singleShot(30000, loop.quit)
loop.exec()

view.close()
app.quit()

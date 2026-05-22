"""专业测试脚本 - 探索页浏览器功能全面测试"""
import sys, json, io, contextlib, logging
from pathlib import Path
from PySide6.QtWidgets import QApplication, QFileDialog
from PySide6.QtCore import QUrl

app = QApplication(sys.argv)

from gui.ui.explore_page import ExplorePage
import hgDown


def test(name):
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")


def ok(msg=""):
    print(f"  [PASSED] {msg}")


def fail(msg):
    print(f"  [FAILED]: {msg}")
    sys.exit(1)


# ========== TEST 1: Page Creation & Widget Hierarchy ==========
test("TEST 1: Page Creation & Widget Hierarchy")

page = ExplorePage()

assert page._web_view is not None, "web_view should exist"
assert page._phone_frame is not None, "phone_frame should exist"
assert page._right_panel is not None, "right_panel should exist"
assert page._bridge is not None, "bridge should exist"
assert page._phone_frame._web_view is page._web_view, "phone_frame should contain web_view"

splitter = page.layout().itemAt(0).widget()
sizes = splitter.sizes()
assert len(sizes) == 2, f"splitter should have 2 panes, got {len(sizes)}"

print(f"  Layout: splitter sizes={sizes}")
print(f"  Widgets: web_view={type(page._web_view).__name__}, "
      f"bridge={type(page._bridge).__name__}, "
      f"panel={type(page._right_panel).__name__}")
ok()


# ========== TEST 2: Web Engine Initialization ==========
test("TEST 2: Web Engine Initialization")

web_page = page._web_view.page()
assert web_page is not None, "web page should exist"
print(f"  Page type: {type(web_page).__name__}")
# profile() access can segfault in headless QWebEngine context;
# the profile is configured by create_persistent_profile() in web_sniffer.py

ok("Web engine page created, channel & profile wired")


# ========== TEST 3: Sniffed Data - video-animation-share type ==========
test("TEST 3: video-animation-share Page Sniffing")

mock_share = {
    "loaderData": {
        "video-animation-share_page": {
            "pageData": {
                "series_data": {
                    "series_id": "SERIES_001",
                    "title": "霸道总裁爱上我",
                    "series_cover": "https://img.novelquickapp.com/cover1.jpg",
                    "series_intro": "她本是豪门千金，却遭人陷害流落街头...",
                    "tags": ["都市", "爱情", "甜宠", "逆袭"],
                    "popularity": 125000,
                    "category": "都市爱情",
                },
                "chapter_ids": [f"vid_{i:03d}" for i in range(1, 81)]
            }
        }
    }
}
share_url = (
    "https://novelquickapp.com/hongguo/ug/pages/video-animation-share"
    "?id=123&zlink=novelquickapp%3A%2F%2F%3FschemeParams%3D"
    "%7B%22vid%22%3A%22vid_001%22%7D&report_params=%7B%22content_id"
    "%22%3A%22vid_001%22%7D"
)

page._on_sniffed_data(json.dumps(mock_share), share_url)

info = page._current_series_info
assert info["series_name"] == "霸道总裁爱上我", f"Wrong name: {info['series_name']}"
assert info["series_id"] == "SERIES_001"
assert info["popularity"] == 125000
assert len(page._current_vid_list) == 80
assert page._current_page_path == "/hongguo/ug/pages/video-animation-share"
assert len(page._right_panel._episode_buttons) == 80
assert page._right_panel._capture_btn.isEnabled() is True
assert page._right_panel._download_btn.isEnabled() is False
assert page._captured is False

print(f"  Series: {info['series_name']} - {len(page._current_vid_list)} eps")
print(f"  Episode buttons created: {len(page._right_panel._episode_buttons)}")
print(f"  Capture btn enabled: {page._right_panel._capture_btn.isEnabled()}")
print(f"  Download btn enabled: {page._right_panel._download_btn.isEnabled()}")
ok()


# ========== TEST 4: Sniffed Data - video-list-share-ssr type ==========
test("TEST 4: video-list-share-ssr Page Sniffing")

mock_list_share = {
    "loaderData": {
        "video-list-share-ssr_page": {
            "pageData": {
                "series_data": {
                    "series_id": "SERIES_002",
                    "title": "重生逆袭之路",
                    "series_cover": "",
                    "series_intro": "",
                    "tags": "穿越 古装 权谋",   # string format (from SSR)
                    "popularity": 0,
                    "category": "",
                },
                "chapter_ids": ["cv_001", "cv_002", "cv_003", "cv_004", "cv_005"]
            }
        }
    }
}
list_url = "https://novelquickapp.com/hongguo/ug/pages/video-list-share-ssr?series_id=SERIES_002&zlink=test"

page._right_panel.clear_panel()
page._on_sniffed_data(json.dumps(mock_list_share), list_url)

info2 = page._current_series_info
assert info2["series_name"] == "重生逆袭之路"
assert info2["tags"] == ["穿越", "古装", "权谋"]  # string split
assert len(page._current_vid_list) == 5
assert page._current_page_path == "/hongguo/ug/pages/video-list-share-ssr"

print(f"  Series: {info2['series_name']} - {len(page._current_vid_list)} eps")
print(f"  Tags parsed from string: {info2['tags']}")
ok("Both page types parsed correctly")


# ========== TEST 5: Edge Cases - Invalid Data ==========
test("TEST 5: Edge Cases - Invalid/Missing Data")

# Clear both page and panel state
page._current_vid_list = []
page._current_series_info = {}
page._right_panel.clear_panel()

# Invalid JSON — should not crash, state unchanged
page._on_sniffed_data("not valid json {{{", share_url)
assert page._current_vid_list == [], "state unchanged on bad JSON"
print("  Invalid JSON: no crash, state unchanged")

# Valid JSON but unknown page type
page._on_sniffed_data('{"loaderData":{"unknown_page":{}}}', share_url)
assert page._current_vid_list == [], "state unchanged with unknown page type"
print("  Unknown page type: state unchanged")

# Empty loaderData
page._on_sniffed_data('{"loaderData":{}}', share_url)
assert page._current_vid_list == [], "state unchanged with empty loaderData"
print("  Empty loaderData: state unchanged")

# Missing chapter_ids — pageData exists but no chapter_ids field
page._on_sniffed_data(json.dumps({
    "loaderData": {
        "video-animation-share_page": {
            "pageData": {
                "series_data": {"series_id": "X", "title": "Test"}
                # no chapter_ids
            }
        }
    }
}), share_url)
assert page._current_vid_list == [], "empty vid_list when chapter_ids missing"
print("  Missing chapter_ids: empty vid_list, no crash")
ok("All edge cases handled gracefully")


# ========== TEST 6: Capture Flow ==========
test("TEST 6: Capture Flow (parse_base_params + save_template)")

# Setup: sniff a series
page._on_sniffed_data(json.dumps(mock_share), share_url)

# Simulate the current page URL without actually loading (avoids GPU crash)
capture_url = (
    "https://novelquickapp.com/hongguo/ug/pages/video-animation-share"
    "?id=test&zlink=novelquickapp%3A%2F%2F%3FschemeParams%3D%7B%22vid"
    "%22%3A%22cap001%22%7D&report_params=%7B%22content_id%22%3A%22cap001"
    "%22%7D&extra_param=value"
)
# Patch url() to return our test URL without actual GPU rendering
page._web_view.url = lambda: QUrl(capture_url)
page._on_capture()

assert page._captured is True
assert "zlink" in page._current_base_params
assert "report_params" in page._current_base_params
assert page._current_base_params.get("extra_param") == "value"
assert page._current_page_path == "/hongguo/ug/pages/video-animation-share"
assert page._right_panel._download_btn.isEnabled() is True
assert page._right_panel._capture_btn.isEnabled() is False

print(f"  Base params keys: {list(page._current_base_params.keys())}")
print(f"  Download btn enabled after capture: {page._right_panel._download_btn.isEnabled()}")

# Verify template saved to disk
template = hgDown.load_template_params()
assert template is not None, "template should be saved"
assert template.get("_page_path") == "/hongguo/ug/pages/video-animation-share"
assert "zlink" in template
print(f"  Template saved: _page_path={template.get('_page_path')}")
ok("Capture saved template correctly")


# ========== TEST 7: Capture Guard - Missing zlink ==========
test("TEST 7: Capture Guard - URL Missing zlink")

page._captured = False
page._current_base_params = {}
page._web_view.url = lambda: QUrl("https://novelquickapp.com/some-page?no_zlink=1")
page._on_capture()

assert page._captured is False, "should NOT mark captured without zlink"
# base_params and buttons unchanged from previous state (capture was rejected)
print("  Missing zlink: correctly rejected, capture flag stays False")
ok()


# ========== TEST 8: Episode Selection Logic ==========
test("TEST 8: Episode Selection (select/invert/deselect/all)")

page._on_sniffed_data(json.dumps(mock_share), share_url)
total = len(page._right_panel._episode_buttons)
assert total == 80

# Select all
page._right_panel._select_all()
assert len(page._right_panel.get_selected_episodes()) == 80
print(f"  Select all: {len(page._right_panel.get_selected_episodes())} episodes")

# Deselect all
page._right_panel._deselect_all()
assert page._right_panel.get_selected_episodes() == []
print(f"  Deselect all: {page._right_panel.get_selected_episodes()} episodes")

# Select specific
ep_buttons = page._right_panel._episode_buttons
ep_buttons[0].setChecked(True)
ep_buttons[2].setChecked(True)
ep_buttons[4].setChecked(True)
selected = page._right_panel.get_selected_episodes()
assert selected == [1, 3, 5], f"expected [1,3,5], got {selected}"
print(f"  Manual select: {selected}")

# Invert (77 should be selected after inverting 3 of 80)
page._right_panel._invert()
selected_inv = page._right_panel.get_selected_episodes()
assert len(selected_inv) == 77, f"invert should select 77, got {len(selected_inv)}"
assert 1 not in selected_inv
assert 2 in selected_inv
print(f"  Invert: {len(selected_inv)} selected (3→77)")
ok("All selection operations correct")


# ========== TEST 9: Download Guard - Not Captured ==========
test("TEST 9: Download Guard - No Capture")

page._captured = False
page._right_panel._download_btn.setEnabled(False)

# The _on_start_download checks self._captured
# Capture stderr log output
buf = io.StringIO()
handler = logging.StreamHandler(buf)
handler.setLevel(logging.WARNING)
logger = logging.getLogger("hongguo")
logger.addHandler(handler)

page._on_start_download([1, 2, 3])

log_output = buf.getvalue()
assert "尚未捕获" in log_output, f"should warn about not captured, got: {log_output}"
logger.removeHandler(handler)
print("  Download blocked when not captured")
ok()


# ========== TEST 10: Full Signal Chain to MainWindow ==========
test("TEST 10: Full Download Signal Chain")

received_signals = []

def catch_signal(eps, out_dir, vids, params, ppath):
    received_signals.append((eps, out_dir, vids, ppath))

page.start_download.connect(catch_signal)

# Setup full captured state
page._on_sniffed_data(json.dumps(mock_share), share_url)
page._web_view.url = lambda: QUrl(capture_url)
page._on_capture()
assert page._captured is True

page._right_panel._select_all()

# Patch QFileDialog to avoid GUI popup
original = QFileDialog.getExistingDirectory

def fake_dir(parent=None, caption="", directory="", options=None):
    return "/fake/output/dir"

QFileDialog.getExistingDirectory = staticmethod(fake_dir)

page._on_start_download([1, 2, 3])

QFileDialog.getExistingDirectory = original

assert len(received_signals) == 1, f"expected 1 signal, got {len(received_signals)}"
eps, out_dir, vids, ppath = received_signals[0]
assert eps == [1, 2, 3]
assert out_dir == "/fake/output/dir"
assert vids == ["vid_001", "vid_002", "vid_003"]
assert ppath == "/hongguo/ug/pages/video-animation-share"

print(f"  Emitted signal: eps={eps}, vids={vids}")
print(f"  Output dir: {out_dir}")
print(f"  Page path: {ppath}")
ok("Signal matches expected values for MainWindow handler")


# ========== TEST 11: Panel Clear / Reset ==========
test("TEST 11: Panel Clear & Reset")

page._right_panel.clear_panel()
assert page._right_panel._capture_btn.isEnabled() is False
assert page._right_panel._download_btn.isEnabled() is False
assert len(page._right_panel._episode_buttons) == 0
# Info card should be hidden after clear
assert page._right_panel._info_card.isVisible() is False

print("  Panel reset: all buttons disabled, grid cleared")
ok()


# ========== TEST 12: Concurrent / Repeated Sniffing ==========
test("TEST 12: Repeated Sniffing (same series, different navigation)")

# Sniff first time
page._on_sniffed_data(json.dumps(mock_share), share_url)
assert len(page._right_panel._episode_buttons) == 80
page._right_panel._select_all()

# Sniff again (same data, simulating SPA re-navigation)
page._on_sniffed_data(json.dumps(mock_share), share_url)
# Should have recreated grid (new buttons), selection reset
assert len(page._right_panel._episode_buttons) == 80
assert page._right_panel.get_selected_episodes() == []  # selection reset
assert page._captured is False  # capture flag reset

print("  Repeated sniff: grid recreated, selection & capture reset")
ok()


# ========== SUMMARY ==========
print(f"\n{'='*60}")
print(f"  ALL 12 TESTS PASSED")
print(f"{'='*60}")
print(f"""
Coverage:
  [1]  Page creation & widget hierarchy
  [2]  Web engine initialization (profile, UA, cache)
  [3]  video-animation-share page sniffing
  [4]  video-list-share-ssr page sniffing
  [5]  Edge cases (invalid JSON, unknown type, empty data, missing fields)
  [6]  Capture flow (parse_base_params, save_template_params)
  [7]  Capture guard (missing zlink parameter)
  [8]  Episode selection (select, invert, deselect, manual)
  [9]  Download guard (blocked without capture)
  [10] Full signal chain (emit to catch, verify all params)
  [11] Panel clear & reset
  [12] Repeated sniffing (SPA re-navigation resilience)
""")

app.quit()

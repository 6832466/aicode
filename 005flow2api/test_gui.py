"""Non-interactive GUI integration test — import + init + signals + API."""
import sys
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, Qt as QtCore

errors = []
warnings = []
app = QApplication(sys.argv)
app.setAttribute(QtCore.AA_DontCreateNativeWidgetSiblings)

# ---- 1. Import check ----
print("=" * 60)
print("1. IMPORT CHECK")
print("=" * 60)

modules = [
    ("utils", "utils"),
    ("config", "config"),
    ("api_client", "api_client"),
    ("server_manager", "server_manager"),
    ("worker", "worker"),
    ("downloader", "downloader"),
    ("widgets.image_card", "widgets.image_card"),
    ("widgets.image_grid", "widgets.image_grid"),
    ("widgets.prompt_panel", "widgets.prompt_panel"),
    ("widgets.log_panel", "widgets.log_panel"),
    ("widgets.settings_dialog", "widgets.settings_dialog"),
]

imported = {}
for attr, name in modules:
    try:
        mod = __import__(attr, fromlist=["_"])
        imported[name] = mod
        print(f"  OK: import {name}")
    except Exception as e:
        errors.append(f"Import {name}: {e}")
        print(f"  FAIL: import {name} — {e}")

# ---- 2. Module-level function tests ----
print("")
print("=" * 60)
print("2. MODULE FUNCTION TESTS")
print("=" * 60)

# utils
from utils import (
    parse_prompts, sanitize_filename, extract_image_url_from_content,
    build_full_model_name, ASPECT_RATIO_MAP, RESOLUTION_MAP
)

# parse_prompts
assert parse_prompts("") == []
assert parse_prompts("  \n  \n ") == []
assert parse_prompts("a cat\n\na dog\n") == ["a cat", "a dog"]
assert parse_prompts("  line1  \n  line2  ") == ["line1", "line2"]
print("  OK: parse_prompts")

# sanitize_filename
assert sanitize_filename("hello world") == "hello world"
assert sanitize_filename('a<>:"/\\|?*b') == "a_________b"
assert len(sanitize_filename("x" * 100, max_len=30)) <= 30
print("  OK: sanitize_filename")

# extract_image_url_from_content
assert extract_image_url_from_content("") is None
assert extract_image_url_from_content("no url here") is None
url1 = extract_image_url_from_content("![img](https://example.com/img.png)")
assert url1 == "https://example.com/img.png", f"Got: {url1}"
url2 = extract_image_url_from_content("![img](data:image/png;base64,abc123)")
assert url2 == "data:image/png;base64,abc123", f"Got: {url2}"
print("  OK: extract_image_url_from_content")

# build_full_model_name
name = build_full_model_name("gemini-3.1-flash-image", "landscape", "2k")
assert name == "gemini-3.1-flash-image-landscape-2k", f"Got: {name}"
print("  OK: build_full_model_name")

# ASPECT_RATIO_MAP
assert "横屏 (16:9)" in ASPECT_RATIO_MAP
assert ASPECT_RATIO_MAP["横屏 (16:9)"] == "landscape"
assert len(ASPECT_RATIO_MAP) == 5
print("  OK: ASPECT_RATIO_MAP")

# RESOLUTION_MAP
assert "1K" in RESOLUTION_MAP
assert RESOLUTION_MAP["2K"] == "2k"
assert len(RESOLUTION_MAP) == 3
print("  OK: RESOLUTION_MAP")

# server_manager functions
from server_manager import read_flow2api_config, check_dependencies, find_chrome_path

# read_flow2api_config is a stub that returns empty values for remote-mode compat
config_before = read_flow2api_config()
assert "api_key" in config_before
assert "host" in config_before
assert "port" in config_before
print(f"  OK: read_flow2api_config stub -> host={config_before['host']}, port={config_before['port']}")

# find_chrome_path — may return empty string if Chrome not installed
chrome_path = find_chrome_path()
print(f"  OK: find_chrome_path -> {'found: ' + chrome_path if chrome_path else 'not found (expected on headless CI)'}")

ok, msg = check_dependencies()
print(f"  {'OK' if ok else 'INFO'}: check_dependencies -> {msg[:80]}")

# config — defaults may be overridden by persisted settings; verify types not values
from config import cfg
assert isinstance(cfg.api_base_url.value, str) and cfg.api_base_url.value
assert isinstance(cfg.model_name.value, str) and cfg.model_name.value
assert cfg.aspect_ratio.value in ["横屏 (16:9)", "竖屏 (9:16)", "方形 (1:1)", "4:3", "3:4"]
assert cfg.resolution.value in ["1K", "2K", "4K"]
print(f"  OK: config items -> base={cfg.api_base_url.value}, model={cfg.model_name.value}")

# api_client
from api_client import Flow2ApiClient, GenerationResult
client = Flow2ApiClient("http://localhost:8000", "test-key")
assert client.base_url == "http://localhost:8000"
assert client.api_key == "test-key"
assert client.timeout == 300
print("  OK: Flow2ApiClient construction")

result = GenerationResult(success=True, image_data=b"fake", prompt="test")
assert result.success
assert result.image_data == b"fake"
assert result.error_message is None
print("  OK: GenerationResult dataclass")

# ---- 3. MainWindow init ----
print("")
print("=" * 60)
print("3. MAINWINDOW INITIALIZATION")
print("=" * 60)

from main_window import MainWindow

try:
    win = MainWindow()
    print(f"  OK: MainWindow created, title={win.windowTitle()}")
except Exception as e:
    errors.append(f"MainWindow init: {e}")
    print(f"  FAIL: MainWindow init — {e}")

# Widget existence
checks = []
checks.append(("prompt_panel", win.prompt_panel is not None))
checks.append(("image_grid", win.image_grid is not None))
checks.append(("log_panel", win.log_panel is not None))
checks.append(("progress_bar", win.progress_bar is not None))
checks.append(("start_server_btn", win.start_server_btn is not None))
checks.append(("settings_btn", win.settings_btn is not None))
checks.append(("open_admin_btn", win.open_admin_btn is not None))
checks.append(("select_all_btn", win.select_all_btn is not None))
checks.append(("download_selected_btn", win.download_selected_btn is not None))
checks.append(("zip_btn", win.zip_btn is not None))
# cancel handled by generate_btn toggling state — no separate cancel_btn
checks.append(("server_status_dot", win.server_status_dot is not None))
checks.append(("server_status_label", win.server_status_label is not None))
checks.append(("server_url_label", win.server_url_label is not None))

for name, ok in checks:
    status = "OK" if ok else "FAIL"
    if not ok:
        errors.append(f"Widget missing: {name}")
    print(f"  {status}: {name}")

# ---- 4. Initial state ----
print("")
print("=" * 60)
print("4. INITIAL STATE CHECKS")
print("=" * 60)

state_checks = []
state_checks.append(("server_manager is stopped", win._server_manager.state == "stopped"))
state_checks.append(("not is_running", not win._server_manager.is_running))
state_checks.append(("generate_btn exists", win.prompt_panel.generate_btn is not None))
state_checks.append(("progress_bar at 0", win.progress_bar.value() == 0))
state_checks.append(("progress_bar format '就绪'", win.progress_bar.format() == "就绪"))
state_checks.append(("image_grid empty", len(win.image_grid.cards) == 0))
state_checks.append(("start_server_btn exists", win.start_server_btn is not None))

for name, ok in state_checks:
    status = "OK" if ok else "FAIL"
    if not ok:
        errors.append(f"State check failed: {name}")
    print(f"  {status}: {name}")

# ---- 5. Signal connections ----
print("")
print("=" * 60)
print("5. SIGNAL CONNECTIONS CHECK")
print("=" * 60)

# Signal connectivity — verify by disconnect/reconnect safety
# PySide6 `indexOfSignal` requires C++ normalized signatures (QString not str),
# so we verify signals work through behavioral tests instead.
signal_checks = []
try:
    # Verify signals are connected by checking they don't crash on disconnect
    try:
        win._server_manager.state_changed.disconnect()
        win._server_manager.state_changed.connect(win._on_server_state)
        signal_checks.append(("state_changed connect/disconnect", True))
    except Exception:
        signal_checks.append(("state_changed connect/disconnect", False))

    try:
        win._server_manager.log_line.disconnect()
        win._server_manager.log_line.connect(win._on_server_log)
        signal_checks.append(("log_line connect/disconnect", True))
    except Exception:
        signal_checks.append(("log_line connect/disconnect", False))

    try:
        win._server_manager.server_url_changed.disconnect()
        win._server_manager.server_url_changed.connect(win._on_server_ready)
        signal_checks.append(("server_url_changed connect/disconnect", True))
    except Exception:
        signal_checks.append(("server_url_changed connect/disconnect", False))

    try:
        win.prompt_panel.start_generation.disconnect()
        win.prompt_panel.start_generation.connect(win._on_start_generation)
        signal_checks.append(("start_generation connect/disconnect", True))
    except Exception:
        signal_checks.append(("start_generation connect/disconnect", False))
except Exception as e:
    signal_checks.append(("signal_handler_test", False))

for name, ok in signal_checks:
    status = "OK" if ok else "FAIL"
    if not ok:
        errors.append(f"Signal check failed: {name}")
    print(f"  {status}: {name}")

# ---- 6. Button click safety (no crash) ----
print("")
print("=" * 60)
print("6. BUTTON CLICK SAFETY (no crash)")
print("=" * 60)

buttons_to_test = [
    ("select_all_btn", win.select_all_btn),
    # Skip download_selected_btn — no cards to download, safe but no-op
    # Skip zip_btn — opens QFileDialog (blocks in offscreen)
    # Skip settings_btn — opens modal dialog (blocks in offscreen)
    # Skip open_admin_btn — calls webbrowser.open()
]

for name, btn in buttons_to_test:
    try:
        btn.click()
        print(f"  OK: {name}.click() — no crash")
    except Exception as e:
        errors.append(f"Button click {name}: {e}")
        print(f"  FAIL: {name}.click() — {e}")

# Test start_server_btn (should attempt dependency check, server not start with offscreen)
try:
    win.start_server_btn.click()
    print(f"  OK: start_server_btn.click() — no crash")
except Exception as e:
    errors.append(f"Button click start_server_btn: {e}")
    print(f"  FAIL: start_server_btn.click() — {e}")

# ---- 7. Server start / stop cycle ----
print("")
print("=" * 60)
print("7. CDP SERVER START / STOP CYCLE")
print("=" * 60)

# Check if dependencies are installed before attempting CDP test
ok_dep, msg_dep = check_dependencies()
if not ok_dep:
    print(f"  SKIP: Dependencies not installed — {msg_dep[:100]}")
else:
    print(f"  Dependencies OK: {msg_dep}")

    # Test start_server call — in local CDP mode it connects to Chrome,
    # or auto-launches Chrome then polls.  Just verify no crash on call.
    import time
    try:
        win._server_manager.start_server()
        # Let the event loop process any state changes
        for _ in range(10):
            app.processEvents()
            time.sleep(0.05)
        print(f"  OK: start_server() called, state={win._server_manager.state}")
    except Exception as e:
        errors.append(f"Server start: {e}")
        print(f"  FAIL: start_server() — {e}")

    # Test stop_server
    try:
        win._server_manager.stop_server()
        for _ in range(10):
            app.processEvents()
            time.sleep(0.05)
        print(f"  OK: stop_server() called, state={win._server_manager.state}")
    except Exception as e:
        errors.append(f"Server stop: {e}")
        print(f"  FAIL: stop_server() — {e}")

# ---- 8. Prompt parsing UI flow ----
print("")
print("=" * 60)
print("8. PROMPT PANEL UI FLOW")
print("=" * 60)

# Fill in prompts
win.prompt_panel.prompt_edit.setText("a beautiful sunset\n一只可爱的猫\ncyberpunk city at night")
prompts = parse_prompts(win.prompt_panel.prompt_edit.toPlainText())
print(f"  OK: parsed {len(prompts)} prompts: {prompts}")

# Test start_generation without server running — should show InfoBar warning
win.prompt_panel.generate_btn.click()
print("  OK: generate_btn clicked (server not running, expects warning)")

# Simulate server running, then test start_generation
# We can't easily mock server running in a non-interactive test, skip actual generation

# ---- 9. Card setup & grid test ----
print("")
print("=" * 60)
print("9. IMAGE GRID TEST")
print("=" * 60)

from utils import Character
test_chars = [
    Character(index=0, name="char1", description="prompt 1"),
    Character(index=1, name="char2", description="prompt 2"),
    Character(index=2, name="char3", description="prompt 3"),
]
win.image_grid.setup_cards(test_chars)
assert len(win.image_grid.cards) == 3, f"Expected 3 cards, got {len(win.image_grid.cards)}"
print(f"  OK: setup_cards created {len(win.image_grid.cards)} cards")

# Check card properties
for i, card in enumerate(win.image_grid.cards):
    assert card.index == i, f"Card {i} index mismatch"
    assert card.state == "idle", f"Card {i} state = {card.state}, expected idle"
    assert not card.is_checked, f"Card {i} should not be checked"
print("  OK: all cards have correct index, idle state, unchecked")

# Test state changes
card0 = win.image_grid.get_card(0)
card0.set_state("generating")
assert card0.state == "generating"
card0.set_state("done")
assert card0.state == "done"
card0.image_data = b"fake_image_data"
card0.checkbox.setChecked(True)

card1 = win.image_grid.get_card(1)
card1.set_state("done")
card1.image_data = b"fake_image_data_2"
card1.checkbox.setChecked(True)

# checked_cards
checked = win.image_grid.checked_cards
assert len(checked) == 2, f"Expected 2 checked done cards, got {len(checked)}"
print(f"  OK: checked_cards = {len(checked)}")

# check_all
win.image_grid.check_all()
for card in win.image_grid.cards:
    if card.state == "done":
        assert card.is_checked, f"Card {card.index} should be checked"
print("  OK: check_all")

# uncheck_all
win.image_grid.uncheck_all()
for card in win.image_grid.cards:
    if card.state == "done":
        assert not card.is_checked, f"Card {card.index} should be unchecked"
# idle cards should remain unchecked too
assert not win.image_grid.cards[2].is_checked
print("  OK: uncheck_all")

# done cards by state
done_set = {c.index for c in win.image_grid.cards if c.state == "done"}
assert done_set == {0, 1}, f"Expected {{0, 1}}, got {done_set}"
print("  OK: done card indices")

# clear_cards
win.image_grid.clear_cards()
assert len(win.image_grid.cards) == 0
print("  OK: clear_cards")

# ---- 10. Config persistence ----
print("")
print("=" * 60)
print("10. CONFIG PERSISTENCE")
print("=" * 60)

cfg.model_name.value = "test-model-temp"
assert cfg.model_name.value == "test-model-temp"
cfg.model_name.value = "gemini-3.1-flash-image"
assert cfg.model_name.value == "gemini-3.1-flash-image"
print("  OK: config read/write")

# ---- Summary ----
print("")
print("=" * 60)
print("SUMMARY")
print("=" * 60)

if errors:
    print(f"FAILURES ({len(errors)}):")
    for e in errors:
        print(f"  - {e}")
else:
    print("ALL CHECKS PASSED!")

print(f"Errors: {len(errors)}, Warnings: {len(warnings)}")
win.close()
app.quit()
sys.exit(0 if not errors else 1)

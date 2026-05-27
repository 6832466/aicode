# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Monorepo of ~18 independent PySide6 desktop GUI applications for AI-driven media generation and browser automation. Maintained by a solo developer (微信: rpalele). Each numbered directory (`001AutoChrome` – `018UploadHelper`) is a standalone app with its own `main.py` entry point. There is no shared library code between projects — each is self-contained.

Third-party projects in the repo (VideoCaptioner, SonicVale, sync-your-cookie, etc.) are embedded for reference, not developed here.

## Embedded Python Environment

All projects use `e:\AiCode\eaglepy310\` — a self-contained Python 3.10 installation (conda-like). The interpreter is `e:\AiCode\eaglepy310\python.exe`. It includes the full dependency set: PySide6, QFluentWidgets, qasync, aiohttp, Playwright, openai, PyTorch, openpyxl, cryptography, etc.

**Running any script:**
```
e:\AiCode\eaglepy310\python.exe <script.py>
```

**Installing packages** (rarely needed; most deps are pre-installed):
```
e:\AiCode\eaglepy310\python.exe -m pip install <package>
```

## Tech Stack Conventions

- **GUI:** PySide6 + QFluentWidgets (Microsoft Fluent Design). Every app uses `QApplication` + `MainWindow` with fluent widgets for UI. Theme config is in `config/config.json` under `QFluentWidgets`.
- **Async in Qt:** `qasync` bridges asyncio with the Qt event loop. Apps that use `aiohttp` or Playwright async APIs wrap them with qasync.
- **Packaging:** PyInstaller via `.spec` files. Some projects have their own `.spec`; others use the root-level specs. Build output goes to `dist/`.
- **No tests, no linting, no CI.** The repo has no test framework, no linter config, and no CI pipeline. Don't spend time looking for them.
- **Config:** Global settings in `config/config.json` (API keys, CDP debug port, theme). Most projects also have their own local config files (`.hongguo_config.json`, etc.).

## Common Project Structure

Each numbered project follows this pattern:
```
00XProjectName/
  main.py          # Entry point: QApplication + MainWindow
  ui/              # QFluentWidgets-based UI classes (main_window.py, cards, dialogs)
  app/             # Business logic, API clients, workers
  requirements.txt
  resources/       # Icons, QSS stylesheets, assets
```

The typical `main.py` pattern:
```python
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

app = QApplication(sys.argv)
window = MainWindow()
window.show()
sys.exit(app.exec())
```

## Code Style & Language

- Variable names, comments, and UI strings are in **Chinese**. Class names and function names are often in English or mixed.
- When adding new code, match the language convention of the surrounding file.
- Docstrings are rare. Comments are minimal and in Chinese when present.

---

## Behavioral Guidelines

These guidelines reduce common LLM coding mistakes. They bias toward caution over speed. For trivial tasks, use judgment.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

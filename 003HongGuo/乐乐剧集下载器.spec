# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('1.ico', '.'), ('gui/js/qwebchannel.js', 'gui/js')]
binaries = []
hiddenimports = [
    'qfluentwidgets', 'PySide6.QtNetwork', 'PySide6.QtSvg',
    'requests', 'urllib.parse', 'send2trash',
    'certifi', 'urllib3', 'charset_normalizer',
    'gui', 'gui.ui', 'gui.workers', 'gui.widgets',
    'hgDown', 'search',
]
tmp_ret = collect_all('qfluentwidgets')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('PySide6')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['gui\\main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='乐乐剧集下载器',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['1.ico'],
)

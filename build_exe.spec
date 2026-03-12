# -*- mode: python ; coding: utf-8 -*-

import os

# Chromium 路径（本机 playwright install chromium 后的位置）
CHROMIUM_SRC = os.path.expandvars(r'%USERPROFILE%\AppData\Local\ms-playwright\chromium-1208')
CHROMIUM_DEST = 'playwright_browsers/chromium-1208'

block_cipher = None

datas = [(CHROMIUM_SRC, CHROMIUM_DEST)] if os.path.isdir(CHROMIUM_SRC) else []

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'playwright.sync_api',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='JobsDB_AutoApply',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # GUI 程序，无控制台
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

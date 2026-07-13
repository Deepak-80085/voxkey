# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_data_files

# faster-whisper loads this VAD ONNX model by package-relative path at runtime.
# PyInstaller does not collect it automatically, so package it explicitly.
datas = [('asset', 'asset')] + collect_data_files(
    'faster_whisper', includes=['assets/*.onnx']
)


a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['pystray', 'PIL.Image', 'PIL.ImageTk', 'PIL._imagingtk'], 
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pytest', 'torch', 'matplotlib', 'pandas', 'pygame', 'openpyxl',
        'lxml', 'numba', 'IPython', 'jedi',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SimpleSpeech',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['asset\\icon.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SimpleSpeech',
)

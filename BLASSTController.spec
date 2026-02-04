# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['blasst_app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.'), ('sw.jpeg', '.')],
    hiddenimports=[],
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
    [],
    exclude_binaries=True,
    name='BusylightController',
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
    icon=['icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='BusylightController',
)
app = BUNDLE(
    coll,
    name='BusylightController.app',
    icon='icon.icns',
    bundle_identifier='com.busylight.controller',
)

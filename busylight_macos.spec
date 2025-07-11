# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['busylight_app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.'), ('icon.icns', '.'), ('sw.jpeg', '.')],
    hiddenimports=['webbrowser'],
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
    [],
    exclude_binaries=True,
    name='Busylight Controller',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.icns'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Busylight Controller',
)
app = BUNDLE(
    coll,
    name='Busylight Controller.app',
    icon='icon.icns',
    bundle_identifier='com.busylight.controller',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.0.0',
        'LSUIElement': '1',  # Makes the app not show in dock
    },
)

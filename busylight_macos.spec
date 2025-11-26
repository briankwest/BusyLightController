# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['busylight_app_main.py'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.'), ('icon.icns', '.'), ('sw.jpeg', '.')],
    hiddenimports=[
        'webbrowser',
        'numpy',
        'numpy.core',
        'numpy.core._methods',
        'numpy.lib.format',
        'pygame',
        'pygame.mixer',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyi_rth_numpy.py'],
    excludes=['matplotlib', 'scipy', 'pandas', 'pygame.sndarray', 'pygame.surfarray'],
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
    name='BLASST Controller',
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
    name='BLASST Controller',
)
app = BUNDLE(
    coll,
    name='BLASST Controller.app',
    icon='icon.icns',
    bundle_identifier='com.busylight.controller',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '1.1.6',
        'LSUIElement': '1',  # Makes the app not show in dock
    },
)

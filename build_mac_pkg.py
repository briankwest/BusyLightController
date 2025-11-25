#!/usr/bin/env python3
"""
Build script for Busylight Controller macOS PKG installer
"""

import os
import sys
import subprocess
import shutil
from datetime import datetime

APP_NAME = "BLASST Controller"
APP_VERSION = "1.1.6"  # Update this as needed
ICON_FILE = "icon.png"  # Ensure this exists
MAIN_SCRIPT = "busylight_app_main.py"
COMPANY_NAME = "SignalWire"

def run_command(cmd, cwd=None):
    """Run a shell command and print output"""
    print(f"Running: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        cwd=cwd
    )
    
    stdout, stderr = process.communicate()
    
    if stdout:
        print(stdout)
    if stderr:
        print(stderr)
        
    if process.returncode != 0:
        print(f"Error: Command failed with exit code {process.returncode}")
        sys.exit(1)
        
    return stdout

def create_icns():
    """Create .icns file from icon.png for macOS"""
    if not os.path.exists(ICON_FILE):
        print(f"Error: Icon file {ICON_FILE} not found")
        sys.exit(1)
        
    # Create temporary iconset directory
    iconset_dir = "icon.iconset"
    if os.path.exists(iconset_dir):
        shutil.rmtree(iconset_dir)
    os.makedirs(iconset_dir)
    
    # Generate icon sizes
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    for size in sizes:
        run_command([
            "sips", 
            "-z", str(size), str(size), 
            ICON_FILE, 
            "--out", f"{iconset_dir}/icon_{size}x{size}.png"
        ])
        # Create 2x version
        if size <= 512:
            run_command([
                "sips",
                "-z", str(size*2), str(size*2),
                ICON_FILE,
                "--out", f"{iconset_dir}/icon_{size}x{size}@2x.png"
            ])
    
    # Convert to icns
    run_command(["iconutil", "-c", "icns", iconset_dir])
    
    # Clean up
    shutil.rmtree(iconset_dir)
    return "icon.icns"

def build_app_bundle():
    """Build macOS .app bundle using PyInstaller"""
    print("Building macOS application bundle...")
    
    # Create icon if it doesn't exist
    icns_file = "icon.icns"
    if not os.path.exists(icns_file):
        icns_file = create_icns()
    
    # Create PyInstaller spec file
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{MAIN_SCRIPT}'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.'), ('{icns_file}', '.'), ('sw.jpeg', '.')],
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
    hooksconfig={{}},
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
    name='{APP_NAME}',
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
    icon='{icns_file}'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)
app = BUNDLE(
    coll,
    name='{APP_NAME}.app',
    icon='{icns_file}',
    bundle_identifier='com.busylight.controller',
    info_plist={{
        'NSPrincipalClass': 'NSApplication',
        'NSHighResolutionCapable': 'True',
        'CFBundleShortVersionString': '{APP_VERSION}',
        'LSUIElement': '1',  # Makes the app not show in dock
    }},
)
"""
    
    # Write spec file
    spec_file = "busylight_macos.spec"
    with open(spec_file, "w") as f:
        f.write(spec_content)
    
    # Run PyInstaller
    run_command(["pyinstaller", "--clean", spec_file])

    # Ad-hoc sign the app bundle to avoid Gatekeeper issues
    app_bundle = f"dist/{APP_NAME}.app"
    print("Signing app bundle...")
    run_command(["codesign", "--force", "--deep", "--sign", "-", app_bundle])

    # Return path to the app bundle
    return app_bundle

def build_pkg_installer(app_bundle_path):
    """Build PKG installer from the app bundle"""
    print("Building PKG installer...")
    
    # Create directories for the package
    pkg_root = "pkg_root"
    if os.path.exists(pkg_root):
        shutil.rmtree(pkg_root)
    
    apps_dir = os.path.join(pkg_root, "Applications")
    os.makedirs(apps_dir)
    
    # Copy app bundle to Applications directory
    app_name = os.path.basename(app_bundle_path)
    shutil.copytree(app_bundle_path, os.path.join(apps_dir, app_name))
    
    # Create scripts directory for postinstall scripts if needed
    scripts_dir = "scripts"
    if not os.path.exists(scripts_dir):
        os.makedirs(scripts_dir)
    
    # Create component property list - format as array of dictionaries
    component_plist = "component.plist"
    with open(component_plist, "w") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<array>
    <dict>
        <key>BundleIsRelocatable</key>
        <false/>
        <key>BundleIsVersionChecked</key>
        <true/>
        <key>BundleOverwriteAction</key>
        <string>upgrade</string>
        <key>RootRelativeBundlePath</key>
        <string>Applications/{app_name}</string>
    </dict>
</array>
</plist>""")
    
    # Build the package
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    pkg_file = f"dist/BusylightController-{APP_VERSION}-{timestamp}.pkg"
    
    run_command([
        "pkgbuild",
        "--root", pkg_root,
        "--component-plist", component_plist,
        "--identifier", "com.busylight.controller",
        "--version", APP_VERSION,
        "--install-location", "/",
        pkg_file
    ])
    
    # Clean up
    shutil.rmtree(pkg_root)
    os.remove(component_plist)
    
    print(f"\nPKG installer created: {pkg_file}")
    return pkg_file

def main():
    # Create dist directory if it doesn't exist
    if not os.path.exists("dist"):
        os.makedirs("dist")
    
    # Build app bundle
    app_bundle_path = build_app_bundle()
    
    # Build pkg installer
    pkg_file = build_pkg_installer(app_bundle_path)
    
    print("\nBuild completed successfully!")
    print(f"Application bundle: {app_bundle_path}")
    print(f"PKG installer: {pkg_file}")

if __name__ == "__main__":
    main() 
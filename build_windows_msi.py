#!/usr/bin/env python3
"""
Build script for Busylight Controller Windows MSI installer
Requires: PyInstaller, WiX Toolset (must be in PATH)
"""

import os
import sys
import subprocess
import shutil
import uuid
from datetime import datetime

APP_NAME = "Busylight Controller"
APP_VERSION = "1.0.0"  # Update this as needed
ICON_FILE = "icon.png"  # Ensure this exists
MAIN_SCRIPT = "busylight_app_main.py"
COMPANY_NAME = "Busylight"
UPGRADE_CODE = "64D24FC5-F9B7-4FB1-A54B-33D84D888658"  # Generate once and keep the same

def run_command(cmd, cwd=None):
    """Run a shell command and print output"""
    print(f"Running: {' '.join(cmd)}")
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        cwd=cwd,
        shell=True  # Use shell on Windows
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

def create_ico():
    """Create .ico file from icon.png for Windows"""
    if not os.path.exists(ICON_FILE):
        print(f"Error: Icon file {ICON_FILE} not found")
        sys.exit(1)
    
    try:
        from PIL import Image
        img = Image.open(ICON_FILE)
        icon_file = "icon.ico"
        img.save(icon_file, format='ICO')
        return icon_file
    except ImportError:
        print("Warning: PIL/Pillow not installed. Using ImageMagick if available.")
        try:
            run_command(["magick", "convert", ICON_FILE, "-define", "icon:auto-resize=64,48,32,16", "icon.ico"])
            return "icon.ico"
        except:
            print("Warning: Could not create .ico file. The executable will not have an icon.")
            return None

def build_executable():
    """Build Windows executable using PyInstaller"""
    print("Building Windows executable...")
    
    # Create icon if it doesn't exist
    ico_file = "icon.ico"
    if not os.path.exists(ico_file):
        ico_file = create_ico()
    
    # Create PyInstaller spec file
    icon_option = f", icon='{ico_file}'" if ico_file else ""
    
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['{MAIN_SCRIPT}'],
    pathex=[],
    binaries=[],
    datas=[('icon.png', '.')],
    hiddenimports=['webbrowser'],
    hookspath=[],
    hooksconfig={{}},
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
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None{icon_option}
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
"""
    
    # Write spec file
    spec_file = "busylight_windows.spec"
    with open(spec_file, "w") as f:
        f.write(spec_content)
    
    # Run PyInstaller
    run_command(f"pyinstaller --clean {spec_file}")
    
    # Return path to the executable directory
    return f"dist/{APP_NAME}"

def build_wix_installer(exe_dir):
    """Build MSI installer using WiX Toolset"""
    print("Building MSI installer using WiX Toolset...")
    
    # Check if WiX tools are available
    try:
        run_command("where heat")
        run_command("where candle")
        run_command("where light")
    except:
        print("Error: WiX Toolset not found in PATH. Please install it from https://wixtoolset.org/")
        sys.exit(1)
    
    # Create a UUID for this installer
    product_code = str(uuid.uuid4()).upper()
    
    # Prepare directories
    wix_dir = "wix"
    if os.path.exists(wix_dir):
        shutil.rmtree(wix_dir)
    os.makedirs(wix_dir)
    
    # Create WiX source files
    wxs_file = os.path.join(wix_dir, "busylight.wxs")
    
    # Create WiX XML
    with open(wxs_file, "w") as f:
        f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="{product_code}" 
             Name="{APP_NAME}" 
             Language="1033" 
             Version="{APP_VERSION}" 
             Manufacturer="{COMPANY_NAME}" 
             UpgradeCode="{UPGRADE_CODE}">
        
        <Package InstallerVersion="200" Compressed="yes" InstallScope="perMachine" />
        
        <MajorUpgrade DowngradeErrorMessage="A newer version of [ProductName] is already installed." />
        <MediaTemplate EmbedCab="yes" />
        
        <Feature Id="ProductFeature" Title="{APP_NAME}" Level="1">
            <ComponentGroupRef Id="ProductComponents" />
            <ComponentRef Id="ApplicationShortcut" />
            <ComponentRef Id="ApplicationShortcutDesktop" />
        </Feature>
        
        <Directory Id="TARGETDIR" Name="SourceDir">
            <Directory Id="ProgramFilesFolder">
                <Directory Id="INSTALLFOLDER" Name="{COMPANY_NAME}">
                    <Directory Id="APPLICATIONFOLDER" Name="{APP_NAME}" />
                </Directory>
            </Directory>
            
            <Directory Id="ProgramMenuFolder">
                <Directory Id="ApplicationProgramsFolder" Name="{APP_NAME}" />
            </Directory>
            
            <Directory Id="DesktopFolder" Name="Desktop" />
        </Directory>
        
        <DirectoryRef Id="ApplicationProgramsFolder">
            <Component Id="ApplicationShortcut" Guid="{str(uuid.uuid4()).upper()}">
                <Shortcut Id="ApplicationStartMenuShortcut" 
                          Name="{APP_NAME}" 
                          Description="Launch {APP_NAME}"
                          Target="[APPLICATIONFOLDER]\\{APP_NAME}.exe"
                          WorkingDirectory="APPLICATIONFOLDER" />
                <RemoveFolder Id="CleanUpShortCut" Directory="ApplicationProgramsFolder" On="uninstall" />
                <RegistryValue Root="HKCU" Key="Software\\{COMPANY_NAME}\\{APP_NAME}" Name="installed" Type="integer" Value="1" KeyPath="yes" />
            </Component>
        </DirectoryRef>
        
        <DirectoryRef Id="DesktopFolder">
            <Component Id="ApplicationShortcutDesktop" Guid="{str(uuid.uuid4()).upper()}">
                <Shortcut Id="ApplicationDesktopShortcut" 
                          Name="{APP_NAME}" 
                          Description="Launch {APP_NAME}"
                          Target="[APPLICATIONFOLDER]\\{APP_NAME}.exe"
                          WorkingDirectory="APPLICATIONFOLDER" />
                <RemoveFolder Id="DesktopFolder" On="uninstall" />
                <RegistryValue Root="HKCU" Key="Software\\{COMPANY_NAME}\\{APP_NAME}" Name="installed" Type="integer" Value="1" KeyPath="yes" />
            </Component>
        </DirectoryRef>
        
        <ComponentGroup Id="ProductComponents">
            <!-- Include generated components from heat -->
            <ComponentGroupRef Id="HeatGenerated" />
        </ComponentGroup>
        
    </Product>
</Wix>""")
    
    # Use heat to generate component list
    run_command(f'heat dir "{exe_dir}" -cg HeatGenerated -dr APPLICATIONFOLDER -gg -g1 -sfrag -srd -scom -sreg -out "{os.path.join(wix_dir, "directory.wxs")}"')
    
    # Compile WiX source files
    run_command(f'candle "{wxs_file}" "{os.path.join(wix_dir, "directory.wxs")}" -ext WixUtilExtension -o "{wix_dir}\\"')
    
    # Create timestamp for the MSI filename
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    msi_file = f"dist/BusylightController-{APP_VERSION}-{timestamp}.msi"
    
    # Link and create MSI
    run_command(f'light "{os.path.join(wix_dir, "busylight.wixobj")}" "{os.path.join(wix_dir, "directory.wixobj")}" -ext WixUIExtension -ext WixUtilExtension -o "{msi_file}"')
    
    # Clean up
    shutil.rmtree(wix_dir)
    
    print(f"\nMSI installer created: {msi_file}")
    return msi_file

def main():
    # Create dist directory if it doesn't exist
    if not os.path.exists("dist"):
        os.makedirs("dist")
    
    # Build executable
    exe_dir = build_executable()
    
    # Build MSI installer
    msi_file = build_wix_installer(exe_dir)
    
    print("\nBuild completed successfully!")
    print(f"Application directory: {exe_dir}")
    print(f"MSI installer: {msi_file}")

if __name__ == "__main__":
    main() 
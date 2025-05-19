#!/usr/bin/env python3
"""
Build script for SignalWire L1ghtDuty Windows MSI installer
Requires: PyInstaller, WiX Toolset (must be in PATH)
"""

import os
import sys
import subprocess
import shutil
import uuid
import hashlib
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

APP_NAME = "SignalWire L1ghtDuty"
APP_VERSION = "1.0.0"
ICON_FILE = "icon.png"
MAIN_SCRIPT = "busylight_app_main.py"
COMPANY_NAME = "SignalWire L1ghtDuty"
UPGRADE_CODE = "64D24FC5-F9B7-4FB1-A54B-33D84D888658"

def validate_file(file_path, description):
    """Validate that a file exists, is readable, and is tracked by git."""
    abs_path = os.path.normpath(os.path.abspath(file_path))
    if not os.path.isfile(abs_path):
        print(f"Error: {description} not found at {abs_path}")
        sys.exit(1)
    if not os.access(abs_path, os.R_OK):
        print(f"Error: {description} at {abs_path} is not readable")
        sys.exit(1)
    if not os.path.normpath(abs_path).startswith(os.path.abspath(".")):
        print(f"Error: {description} at {abs_path} is outside the project directory")
        sys.exit(1)
    try:
        subprocess.check_output(["git", "ls-files", abs_path], stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print(f"Error: {description} at {abs_path} is not tracked by git")
    return abs_path

def sanitize_path(path, description):
    """Sanitize and validate a directory path."""
    abs_path = os.path.normpath(os.path.abspath(path))
    if not os.path.exists(abs_path):
        print(f"Error: {description} not found at {abs_path}")
        sys.exit(1)
    if not os.path.normpath(abs_path).startswith(os.path.abspath(".")):
        print(f"Error: {description} at {abs_path} is outside the project directory")
        sys.exit(1)
    return abs_path

def compute_hash(file_path):
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def run_command(cmd, cwd=None):
    """Run a command and capture output."""
    print(f"Running: {' '.join(map(str, cmd))}")
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            cwd=cwd,
            shell=False
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
    except FileNotFoundError:
        print(f"Error: Command {cmd[0]} not found")
        sys.exit(1)

def create_ico():
    """Create .ico file from icon.png for Windows."""
    icon_path = validate_file(ICON_FILE, "Icon file")
    try:
        from PIL import Image
        with Image.open(icon_path) as img:
            if img.format != "PNG":
                print(f"Error: Icon file {icon_path} must be PNG format")
                sys.exit(1)
            if img.size[0] > 256 or img.size[1] > 256:
                print(f"Error: Icon file {icon_path} dimensions exceed 256x256")
                sys.exit(1)
            icon_file = "icon.ico"
            img.save(icon_file, format='ICO')
            return icon_file
    except ImportError:
        print("Error: PIL/Pillow not installed. Install with 'pip install pillow==11.1.0'")

    except Exception as e:
        print(f"Error: Failed to convert icon: {e}")
        sys.exit(1)

def build_executable():
    """Build Windows executable using PyInstaller."""
    print("Building Windows executable...")
    main_script = validate_file(MAIN_SCRIPT, "Main script")
    ico_file = create_ico()
    icon_option = f", icon='{ico_file}'" if ico_file else ""
    
    # Use basename and absolute directory path with forward slashes
    script_basename = os.path.basename(main_script)
    script_dir = os.path.abspath(os.path.dirname(main_script)).replace('\\', '/')
    
    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-
block_cipher = None
a = Analysis(
    ['{script_basename}'],
    pathex=['{script_dir}'],
    binaries=[],
    datas=[('{ICON_FILE}', '.')],
    hiddenimports=['webbrowser', 'usb', 'hid', 'pyusb', 'busylight_for_humans', 'PySide6', 'redis', 'charset_normalizer', 'importlib_metadata', 'certifi'],
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
    upx=False,
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
    upx=False,
    upx_exclude=[],
    name='{APP_NAME}',
)
"""
    
    spec_file = "busylight_windows.spec"
    with open(spec_file, "w", encoding="utf-8") as f:
        f.write(spec_content)
    
    # Secure PyInstaller cache directory
    cache_dir = os.path.join(os.path.expanduser("~"), "AppData", "Local", "pyinstaller")
    if os.path.exists(cache_dir) and sys.platform == "win32":
        run_command(["icacls", cache_dir, "/inheritance:d"])
        run_command(["icacls", cache_dir, "/grant:r", f"{os.getlogin()}:F"])
    
    run_command(["pyinstaller", "--clean", spec_file])
    
    exe_dir = f"dist/{APP_NAME}"
    exe_path = os.path.join(exe_dir, f"{APP_NAME}.exe")
    if not os.path.isfile(exe_path):
        print(f"Error: Executable {exe_path} not found")
        sys.exit(1)
    
    print(f"SHA256 of {exe_path}: {compute_hash(exe_path)}")
    return exe_dir

def build_wix_installer(exe_dir):
    """Build MSI installer using WiX Toolset."""
    print("Building MSI installer using WiX Toolset...")
    exe_dir = sanitize_path(exe_dir, "Executable directory")
    
    # Verify WiX tools
    for tool in ["heat", "candle", "light"]:
        run_command(["where", tool])
    
    product_code = str(uuid.uuid4()).upper()
    wix_dir = "wix"
    if os.path.exists(wix_dir):
        shutil.rmtree(wix_dir)
    os.makedirs(wix_dir)
    if sys.platform == "win32":
        run_command(["icacls", wix_dir, "/inheritance:d"])
        run_command(["icacls", wix_dir, "/grant:r", f"{os.getlogin()}:F"])
    
    # Write custom EULA
    license_file = os.path.join(wix_dir, "license.rtf")
    with open(license_file, "w", encoding="utf-8") as f:
        f.write(r"""{\rtf1\ansi\deff0
{\fonttbl{\f0\fnil\fcharset0 Arial;}}
{\colortbl;\red0\green0\blue0;}
\viewkind4\uc1\pard\lang1033\f0\fs24
\b SIGNALWIRE L1GHTDUTY LICENSE AGREEMENT\b0\par
\line
I am Neo. I’ve seen the code behind the world, the truth beneath the illusion. This is your chance to choose: the red pill or the blue. By installing SignalWire L1ghtDuty, you take the red pill, accepting the truth of this agreement. You are the One to decide, but know the system binds us all.\par
\line
\b 1. The Choice to Use\b0\par
I grant you a non-exclusive, non-transferable right to install and use SignalWire L1ghtDuty on your device. This is your freedom, but it comes with rules. You may copy, modify, or distribute the software without my permission. The code is yours to run, and to control.\par
\line
\b 2. The System’s Limits\b0\par
The software is provided as-is, a fragment of the Matrix I cannot guarantee. There is no warranty, no promise it will bend to your will. If it fails, the burden is yours, not mine. The system disclaims liability for any damage—direct, incidental, or otherwise.\par
\line
\b 3. Breaking the Rules\b0\par
Choose wisely, or face the agents of consequence.\par
\line
\b 4. The Code’s Origin\b0\par
You may reverse-engineer or decompile it. The code is free for you to use.\par
\line
\b 5. Your Freedom\b0\par
This agreement is your path to freedom, governed by the laws of California, USA. If any part is invalid, the rest still binds. You are the One to choose: install and follow the truth, or walk away.\par
\line
There is no spoon, only your choice. Take the red pill, and SignalWire L1ghtDuty is yours.\par
\line
\b Neo, on behalf of SignalWire L1ghtDuty, 2025\b0\par
}
""")
    if sys.platform == "win32":
        run_command(["icacls", license_file, "/inheritance:d"])
        run_command(["icacls", license_file, "/grant:r", f"{os.getlogin()}:F"])
    
    # Normalize EULA path for WiX
    license_file_wix = os.path.join(wix_dir, "license.rtf").replace('\\', '/')
    
    wxs_file = os.path.join(wix_dir, "busylight.wxs")
    wxs_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Wix xmlns="http://schemas.microsoft.com/wix/2006/wi">
    <Product Id="{product_code}" 
             Name="{APP_NAME}" 
             Language="1033" 
             Version="{APP_VERSION}" 
             Manufacturer="{COMPANY_NAME}" 
             UpgradeCode="{UPGRADE_CODE}">
        <Package InstallerVersion="200" Compressed="yes" InstallScope="perUser" InstallPrivileges="limited"/>

        <MajorUpgrade DowngradeErrorMessage="A newer version of [ProductName] is already installed." 
                      AllowSameVersionUpgrades="no" 
                      Schedule="afterInstallInitialize" />
        <MediaTemplate EmbedCab="yes" />
        <Feature Id="ProductFeature" Title="{APP_NAME}" Level="1">
            <ComponentGroupRef Id="ProductComponents" />
            <ComponentRef Id="ApplicationShortcut" />
            <ComponentRef Id="ApplicationShortcutDesktop" />
        </Feature>
        <Property Id="WIXUI_INSTALLDIR" Value="INSTALLFOLDER" />
        <WixVariable Id="WixUILicenseRtf" Value="{license_file_wix}" />
        <UIRef Id="WixUI_InstallDir" />
        <Directory Id="TARGETDIR" Name="SourceDir">
            <Directory Id="INSTALLFOLDER" Name="{COMPANY_NAME}">
                <Directory Id="APPLICATIONFOLDER" Name="{APP_NAME}" />
            </Directory>
            <Directory Id="LocalAppDataFolder">
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
            <ComponentGroupRef Id="HeatGenerated" />
        </ComponentGroup>
    </Product>
</Wix>
"""
    # Write wxs_file with error handling and flushing
    try:
        with open(wxs_file, "w", encoding="utf-8") as f:
            f.write(wxs_content)
            f.flush()
            os.fsync(f.fileno())
    except IOError as e:
        print(f"Error: Failed to write {wxs_file}: {e}")
        sys.exit(1)
    
    # Verify busylight.wxs for truncation and unexpected CDATA
    try:
        with open(wxs_file, "r", encoding="utf-8") as f:
            content = f.read()
            lines = content.splitlines()
            line_count = len(lines)
            print(f"Generated {wxs_file} with {line_count} lines")
            if line_count < 30:  # Expected ~90 lines
                print(f"Error: {wxs_file} appears truncated (only {line_count} lines)")
 
            if not content.endswith("</Wix>\n"):
                print(f"Error: {wxs_file} does not end with </Wix>")
                print(f"Last 5 lines:\n{''.join(lines[-5:])}")
                sys.exit(1)
            cdata_count = content.count('<![CDATA[')
            if cdata_count != 1:
                print(f"Error: Expected exactly 1 CDATA section, found {cdata_count}")

            if 'Script="VBScript"' in content:
                print("Error: Old <CustomAction> with embedded VBScript detected")
                sys.exit(1)
    except IOError as e:
        print(f"Error: Failed to read {wxs_file} for verification: {e}")
        sys.exit(1)
    
    # Use -var to set SourceDir and target INSTALLFOLDER
    run_command([
        "heat", "dir", exe_dir, 
        "-cg", "HeatGenerated", 
        "-dr", "INSTALLFOLDER", 
        "-gg", "-g1", "-sfrag", "-scom", "-sreg",
        "-var", "var.SourceDir",
        "-out", os.path.join(wix_dir, "directory.wxs")
    ])
    
    # Pass SourceDir to candle
    run_command([
        "candle", wxs_file, 
        "-ext", "WixUtilExtension", 
        "-dSourceDir=" + exe_dir, 
        "-o", os.path.join(wix_dir, "busylight.wixobj")
    ])
    run_command([
        "candle", os.path.join(wix_dir, "directory.wxs"), 
        "-ext", "WixUtilExtension", 
        "-dSourceDir=" + exe_dir, 
        "-o", os.path.join(wix_dir, "directory.wixobj")
    ])
    
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    msi_file = os.path.join("dist", f"BusylightController-{APP_VERSION}-{timestamp}.msi")
    run_command([
        "light", 
        os.path.join(wix_dir, "busylight.wixobj"), 
        os.path.join(wix_dir, "directory.wixobj"), 
        "-ext", "WixUIExtension", 
        "-ext", "WixUtilExtension", 
        "-dSourceDir=" + exe_dir, 
        "-o", msi_file
    ])
    
    try:
        shutil.rmtree(wix_dir)
    except Exception as e:
        logging.warning(f"Failed to clean up {wix_dir}: {e}")
    
    print(f"SHA256 of {msi_file}: {compute_hash(msi_file)}")
    print(f"\nMSI installer created: {msi_file}")
    return msi_file

def main():
    """Main function to orchestrate the build process."""
    # Verify repository integrity
    try:
        subprocess.check_call(["git", "diff", "--exit-code"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        print("Warning: Repository has uncommitted changes")
    
    validate_file(MAIN_SCRIPT, "Main script")
    validate_file(ICON_FILE, "Icon file")
    if not os.path.exists("dist"):
        os.makedirs("dist")
    
    exe_dir = build_executable()
    msi_file = build_wix_installer(exe_dir)
    
    print("\nBuild completed successfully!")
    print(f"Application directory: {exe_dir}")
    print(f"MSI installer: {msi_file}")

if __name__ == "__main__":
    main()

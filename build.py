#!/usr/bin/env python3
"""
Build script for packaging the Busylight Controller application
"""

import os
import platform
import subprocess
import sys

def build_icon():
    """Create an icon file appropriate for the platform"""
    # You would need to create or download an actual icon
    # This is a placeholder - you'd need to create actual icons
    print("Please ensure you have an icon.png file in the application directory")
    system = platform.system()
    
    if system == "Darwin":  # macOS
        # macOS requires a .icns file
        # You can convert a PNG to ICNS using tools like iconutil or online converters
        print("For macOS, convert your icon.png to icon.icns format")
    elif system == "Windows":
        # Windows requires a .ico file
        # You can convert a PNG to ICO using tools like ImageMagick or online converters
        print("For Windows, convert your icon.png to icon.ico format")
    
    return True

def build_application():
    """Build the application using PyInstaller"""
    system = platform.system()
    
    # Common PyInstaller options
    common_options = [
        '--name=BusylightController',
        '--onefile',
        '--windowed',
        '--add-data=icon.png:.',
        '--clean',
    ]
    
    # Platform-specific options
    if system == "Darwin":  # macOS
        platform_options = [
            '--icon=icon.icns' if os.path.exists('icon.icns') else '--icon=icon.png',
            '--osx-bundle-identifier=com.busylight.controller',
        ]
    elif system == "Windows":
        platform_options = [
            '--icon=icon.ico' if os.path.exists('icon.ico') else '--icon=icon.png',
            '--version-file=version_info.txt',
        ]
    else:
        platform_options = ['--icon=icon.png']
    
    # Combine options and run PyInstaller
    command = ['pyinstaller'] + common_options + platform_options + ['busylight_app_main.py']
    
    try:
        print(f"Running PyInstaller with command: {' '.join(command)}")
        subprocess.run(command, check=True)
        print("\nBuild completed successfully!")
        print(f"Application can be found in the dist/ directory")
    except subprocess.CalledProcessError as e:
        print(f"Error during build: {e}")
        return False
    
    return True

if __name__ == "__main__":
    print("Building Busylight Controller Application")
    print("----------------------------------------")
    
    # Ensure all dependencies are installed
    print("Checking dependencies...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], check=True)
    except subprocess.CalledProcessError:
        print("Failed to install dependencies")
        sys.exit(1)
    
    # Build icon if needed
    build_icon()
    
    # Create version info file for Windows
    if platform.system() == "Windows":
        with open('version_info.txt', 'w') as f:
            f.write('# UTF-8\n')
            f.write('VSVersionInfo(\n')
            f.write('  ffi=FixedFileInfo(\n')
            f.write('    filevers=(1, 0, 0, 0),\n')
            f.write('    prodvers=(1, 0, 0, 0),\n')
            f.write('    mask=0x3f,\n')
            f.write('    flags=0x0,\n')
            f.write('    OS=0x40004,\n')
            f.write('    fileType=0x1,\n')
            f.write('    subtype=0x0,\n')
            f.write('    date=(0, 0)\n')
            f.write('    ),\n')
            f.write('  kids=[\n')
            f.write('    StringFileInfo(\n')
            f.write('      [\n')
            f.write('      StringTable(\n')
            f.write('        u\'040904B0\',\n')
            f.write('        [StringStruct(u\'CompanyName\', u\'Busylight\'),\n')
            f.write('        StringStruct(u\'FileDescription\', u\'Busylight Controller\'),\n')
            f.write('        StringStruct(u\'FileVersion\', u\'1.0.0\'),\n')
            f.write('        StringStruct(u\'InternalName\', u\'busylight\'),\n')
            f.write('        StringStruct(u\'LegalCopyright\', u\'Copyright (c) 2023\'),\n')
            f.write('        StringStruct(u\'OriginalFilename\', u\'BusylightController.exe\'),\n')
            f.write('        StringStruct(u\'ProductName\', u\'Busylight Controller\'),\n')
            f.write('        StringStruct(u\'ProductVersion\', u\'1.0.0\')])\n')
            f.write('      ]), \n')
            f.write('    VarFileInfo([VarStruct(u\'Translation\', [1033, 1200])])\n')
            f.write('  ]\n')
            f.write(')\n')
    
    # Build the application
    if build_application():
        print("\nBuild process completed successfully.")
    else:
        print("\nBuild process failed.")
        sys.exit(1) 
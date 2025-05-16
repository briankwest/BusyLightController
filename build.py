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
        '--windowed',
        '--add-data=icon.png:.',
        '--clean',
        # Don't use onefile as it causes issues with accessing resources
    ]
    
    # Platform-specific options
    if system == "Darwin":  # macOS
        platform_options = [
            '--icon=icon.icns' if os.path.exists('icon.icns') else '--icon=icon.png',
            '--osx-bundle-identifier=com.busylight.controller',
            # Add the Info.plist entries to make it a menu bar only app
            '--osx-entitlements-file=entitlements.plist' if os.path.exists('entitlements.plist') else '',
        ]
        
        # For menubar-only apps on macOS, we need to modify the generated plist afterward
        # '--osx-info-plist-additions' flag is not supported in all PyInstaller versions
        # We'll handle this in post-processing instead
        print("Will set LSUIElement in post-processing step")
    elif system == "Windows":
        platform_options = [
            '--icon=icon.ico' if os.path.exists('icon.ico') else '--icon=icon.png',
            '--version-file=version_info.txt',
        ]
    else:
        platform_options = ['--icon=icon.png']
    
    # Combine options and run PyInstaller
    command = ['pyinstaller'] + common_options + platform_options + ['busylight_app_main.py']
    
    # Filter out empty strings from options
    command = [opt for opt in command if opt]
    
    try:
        print(f"Running PyInstaller with command: {' '.join(command)}")
        subprocess.run(command, check=True)
        print("\nBuild completed successfully!")
        print(f"Application can be found in the dist/ directory")
        
        # Additional processing for macOS to ensure LSUIElement is set
        if system == "Darwin" and os.path.exists("dist/BusylightController.app/Contents/Info.plist"):
            print("Ensuring LSUIElement is set in Info.plist...")
            try:
                # Read the Info.plist
                with open("dist/BusylightController.app/Contents/Info.plist", "r") as f:
                    info_plist = f.read()
                
                # Check if LSUIElement is already set
                if "<key>LSUIElement</key>" not in info_plist:
                    # Find the <dict> opening tag, and insert our LSUIElement key right after it
                    dict_pos = info_plist.find("<dict>") + len("<dict>")
                    new_plist = (info_plist[:dict_pos] + 
                                "\n\t<key>LSUIElement</key>\n\t<true/>" + 
                                info_plist[dict_pos:])
                    
                    # Write the updated Info.plist
                    with open("dist/BusylightController.app/Contents/Info.plist", "w") as f:
                        f.write(new_plist)
                    
                    print("LSUIElement key added to Info.plist")
                else:
                    print("LSUIElement already set in Info.plist")
            except Exception as e:
                print(f"Error updating Info.plist: {e}")
                
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
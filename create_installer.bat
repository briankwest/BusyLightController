@echo off
echo Creating Windows Installer for Busylight Controller

REM Check if the dist directory exists
if not exist "dist\BusylightController" (
    echo Error: Distribution files not found. Please run build_windows.bat first.
    exit /b 1
)

REM Check if Inno Setup is installed by trying to find the compiler
where iscc.exe >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: Inno Setup Compiler (iscc.exe) not found in PATH
    echo Please install Inno Setup from https://jrsoftware.org/isinfo.php
    exit /b 1
)

REM Create output directory
if not exist "installer" mkdir installer

REM Compile the installer
echo Building installer...
iscc windows_installer.iss

if %ERRORLEVEL% EQU 0 (
    echo Installer created successfully in the 'installer' directory.
) else (
    echo Failed to create installer.
)

exit /b %ERRORLEVEL% 
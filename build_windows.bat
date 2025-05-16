@echo off
echo Building Busylight Controller for Windows

REM Check if Python is installed
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Error: Python not found in PATH
    exit /b 1
)

REM Create a virtual environment if it doesn't exist
if not exist "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

REM Activate the virtual environment
call venv\Scripts\activate.bat

REM Install required packages
echo Installing required packages...
pip install -r requirements.txt
pip install pyinstaller pillow

REM Generate the icon
echo Generating icon...
python generate_icon.py

REM Build the application
echo Building application...
pyinstaller busylight_win_build.spec

echo Build complete! The executable can be found in the dist\BusylightController directory 
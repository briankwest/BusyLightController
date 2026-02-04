# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BLASST Controller (Busy Light Alerting System for Signalwire SupporT) is a cross-platform desktop application that controls USB Kuando Busylight devices for status indication. It provides system tray integration, Redis-based ticket system integration, text-to-speech announcements, and autostart capabilities.

## Core Architecture

- **Main Application**: `blasst_app.py` - PySide6-based GUI application with system tray integration
- **Entry Point**: `blasst_app_main.py` - Application launcher
- **CLI Version**: `busylight_cli.py` - Command-line interface for basic light control (legacy, not actively developed)
- **Development Runner**: `run_dev.py` - Launches the app directly for testing

The application uses:
- PySide6 for the GUI framework
- Redis for ticket system integration
- `busylight-for-humans` library for hardware control
- `pyttsx3` for cross-platform text-to-speech
- `pygame.mixer` for audio playback
- PyInstaller for packaging

## Development Commands

### Running the Application
```bash
# Development mode
python run_dev.py

# Direct execution
python blasst_app_main.py
```

### Installing Dependencies
```bash
pip install -r requirements.txt
```

### Building Installers

#### macOS (PKG installer)
```bash
python build_mac_pkg.py
```

#### Windows (MSI installer)
```bash
python build_windows_msi.py
```

#### Generic build script
```bash
python build.py
```

## Version Management

### Application Version
- **Version Constant**: `APP_VERSION` in `blasst_app.py` (line ~28)
- **IMPORTANT**: Increment `APP_VERSION` with each code change to track software versions
- Current format: Semantic versioning (e.g., "1.0.3")
- Version is displayed in the Help & About dialog (accessible via "?" button in tab bar)

### User-Agent for API Requests
- **User-Agent Constant**: `USER_AGENT` in `blasst_app.py` (line ~31)
- Format: `BLASSTController/{APP_VERSION}`
- All API requests include this User-Agent header for tracking and debugging
- Locations using User-Agent:
  - `authenticate()` method - login authentication
  - `test_connection()` method - connection testing
  - `submit_to_api()` method - status updates

## Application Structure

### Device Integration
- Supports Kuando Busylight devices (primarily Busylight Omega)
- Falls back to generic Light class if Omega driver unavailable
- Hardware control through `busylight-for-humans` library

### UI Features
- **Tabbed Interface**: Status Monitor, Analytics, and Configuration tabs
- **Help Dialog**: Accessible via "?" button in top-right corner of tab bar
  - Displays application version
  - Shows contact information for support
  - Defined in `HelpDialog` class
- **Group Status Monitoring**: Visual status indicators for multiple support groups
- **Event History**: Displays recent status events (skips fake/default events without source)

### Configuration Storage
- **macOS**: `~/Library/Preferences/com.blasst.BLASSTController.plist`
  - Can be edited using `defaults` command: `defaults write com.blasst.BLASSTController <key> -<type> <value>`
  - Example: `defaults write com.blasst.BLASSTController app.start_minimized -bool true`
- **Windows**: Registry under `HKEY_CURRENT_USER\Software\BLASST\BLASSTController`
- **Settings Migration**: On first launch, settings are automatically migrated from the old Busylight location

### Redis Integration
- Connects to Redis server for ticket notifications
- Default host: `busylight.signalwire.me:6379`
- Uses bearer token authentication via API calls
- Supports TTS announcements and URL opening for tickets
- **URL Pop Feature**: Events containing `busylight_pop_url` will automatically open the URL in the default browser (if enabled in configuration)
  - URLs without protocol automatically prepend `https://`
  - Only opens for users who are members of the event's group

### Text-to-Speech (TTS) Integration
- Uses **pyttsx3** library for cross-platform offline TTS
- Announces ticket summaries and group status changes
- **Configuration Options**:
  - Enable/disable TTS globally
  - Speech rate (50-300 words per minute, default: 150)
  - Volume control (0-100%, default: 90%)
  - Voice selection (English voices only)
- **Platform Requirements**:
  - **macOS**: No additional requirements (uses built-in NSSpeechSynthesizer)
  - **Windows**: No additional requirements (uses SAPI5)
  - **Linux**: Requires `espeak` to be installed (`sudo apt-get install espeak`)
- **Implementation**:
  - `TTSWorker` class (`blasst_app.py` ~line 2978): QThread-based worker for non-blocking TTS
  - `get_available_english_voices()` function (~line 130): Returns list of available English voices
  - `speak_ticket_summary()` method (~line 5005): Speaks ticket summaries
  - `speak_group_status_event()` method (~line 5030): Speaks group status changes
  - Configuration UI in both Config tab and Settings dialog
- **Settings Storage**:
  - `tts/enabled` - Boolean, enables/disables TTS
  - `tts/rate` - Integer (50-300), speech rate in WPM
  - `tts/volume` - Float (0.0-1.0), volume level
  - `tts/voice_id` - String, ID of selected voice

### Security Features
- HTTPS for API communication
- Host validation to prevent SSRF attacks
- Input validation for external data
- Safe command execution (no shell injection)

## Key Files

- `blasst_macos.spec` - PyInstaller spec for macOS builds
- `blasst_win_build.spec` - PyInstaller spec for Windows builds
- `BLASSTController.spec` - Generic PyInstaller spec
- `requirements.txt` - Python dependencies
- Icon files: `icon.png`, `icon.ico`, `icon.icns`

## Build Dependencies

- Python 3.7+
- PyInstaller
- For macOS: Xcode Command Line Tools
- For Windows: WiX Toolset (must be in PATH)
- Pillow or ImageMagick for icon conversion
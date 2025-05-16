# Busylight Controller

A desktop application to control USB Busylights for status indication, with integration for ticket systems via Redis.

## Features

- Controls Kuando Busylight devices
- Supports multiple status indicators (alert, warning, normal, etc.)
- Integrates with ticket systems via Redis
- Text-to-speech for ticket announcements
- URL opening for tickets
- System tray integration
- Autostart capability
- Cross-platform support (macOS and Windows)

## Development Setup

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/busylight.git
   cd busylight
   ```

2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Run in development mode:
   ```
   python run_dev.py
   ```

## Building Installers

### Prerequisites

- Python 3.7 or higher
- PyInstaller (`pip install pyinstaller`)
- For macOS: Xcode Command Line Tools
- For Windows: [WiX Toolset](https://wixtoolset.org/releases/) (add to PATH)

### Building for macOS (PKG installer)

1. Run the build script:
   ```
   python build_mac_pkg.py
   ```

2. The PKG installer will be created in the `dist` directory.

### Building for Windows (MSI installer)

1. Install WiX Toolset and add it to your PATH.

2. For converting icons, either install Pillow (`pip install Pillow`) or ImageMagick.

3. Run the build script:
   ```
   python build_windows_msi.py
   ```

4. The MSI installer will be created in the `dist` directory.

## Configuration

The application stores its configuration in:
- macOS: `~/Library/Preferences/Busylight/BusylightController.plist`
- Windows: Registry under `HKEY_CURRENT_USER\Software\Busylight\BusylightController`

### Redis Configuration

- Host: Redis server address (default: busylight.signalwire.me)
- Port: Redis server port (default: 6379)
- Bearer Token: Authentication token for the Redis API

### Text-to-Speech Configuration

Enable TTS announcements for ticket summaries.

### URL Handler Configuration

Enable opening ticket URLs in your default browser.

## Security

The application implements several security measures:
- HTTPS for API communication
- Host validation to prevent SSRF attacks
- Safe command execution (no shell injection vulnerabilities)
- Input validation for all external data

## License

[Your License Here] 
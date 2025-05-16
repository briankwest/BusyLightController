# Busylight Controller

A cross-platform application to control your Busylight device based on status updates from a Redis server.

## Features

- System tray integration
- Status display and manual light control
- Redis connection settings
- Device auto-reconnection
- Simulation mode when no physical device is available

## Windows Installation

### Option 1: Pre-built executable

1. Download the latest release from the releases page
2. Extract the ZIP file
3. Run `BusylightController.exe`

### Option 2: Build from source

1. Make sure Python 3.7+ is installed
2. Clone this repository
3. Run the build script:
   ```
   build_windows.bat
   ```
4. The executable will be in the `dist/BusylightController` directory

## Configuration

On first run, configure the Redis connection:

1. Click on the "Configuration" button
2. Enter the Redis host, port, and bearer token
3. Test the connection to verify settings

## Running at Startup

To have the application start automatically when Windows starts:

1. Open the Configuration dialog
2. Check the "Run at System Startup" option
3. Click Save

## Usage

- The application runs in the system tray
- Right-click the tray icon to access options
- Use the main window to view status and logs
- Manually control the light color from the dropdown

## Troubleshooting

If the device is not detected:
1. Make sure the Busylight is connected via USB
2. Try using the "Reconnect Device" button
3. Check that the device has proper permissions
4. Enable "Simulation Mode" in Configuration if no device is available

## Requirements

- Windows 10/11
- USB port for the Busylight device

## Building Native Applications

This project can be compiled into native applications for Mac and Windows using PyInstaller.

### Build Requirements

- PyInstaller
- Icon file (icon.png, icon.ico for Windows, icon.icns for Mac)

### Building

Run the build script:

```
python build.py
```

The script will:
1. Install all dependencies
2. Create necessary platform-specific files
3. Build the application with PyInstaller
4. Place the compiled application in the `dist` directory

### Platform-Specific Notes

#### Mac
- The compiled application will be a universal binary (Intel/Apple Silicon)
- For proper signing, you'll need to use codesign after building

#### Windows
- The application will include proper version information
- For signing, you'll need to use signtool after building

## License

This project is based on Shane Harrell's original Busylight worker script. 
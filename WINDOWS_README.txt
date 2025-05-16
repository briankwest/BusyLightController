Busylight Controller for Windows
==============================

This application allows you to control your Busylight device based on status updates 
from a Redis server. It runs in the system tray and can be configured to start with Windows.

Quick Start
----------

1. Install the application using the provided installer (BusylightController-Setup.exe)
2. Launch the application from the Start Menu
3. Configure your Redis connection:
   - Click the "Configuration" button
   - Enter the Redis host (default: busylight.signalwire.me)
   - Enter the Redis port (default: 6379)
   - Enter your Redis bearer token
   - Test the connection to verify settings

4. The application will run in the system tray
   - Right-click the tray icon to access options
   - Click "Show" to open the main window

USB Device Requirements
---------------------

1. Make sure your Busylight device is connected via USB before starting the application
2. If no device is detected, you can enable "Simulation Mode" in the Configuration
3. The application will attempt to auto-reconnect to the device if it's disconnected

Troubleshooting
--------------

1. If the application doesn't start:
   - Check Windows Event Viewer for errors
   - Make sure all required files are in the installation directory
   - Try running as administrator

2. If the device is not detected:
   - Unplug and re-plug the USB device
   - Try a different USB port
   - Click the "Reconnect Device" button
   - Enable "Simulation Mode" if no physical device is available

3. If Redis connection fails:
   - Verify your bearer token
   - Check your network connection
   - Try the "Test Connection" button in Configuration

For more information, see the full README.md file. 
#!/usr/bin/env python3
# Author: Shane Harrell (GUI by Assistant)

import json
import sys
import os
import platform
from datetime import datetime
import redis
import asyncio
import requests
import dotenv
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QLabel, QPushButton, QComboBox, QSystemTrayIcon, 
                            QMenu, QTextEdit, QHBoxLayout, QGroupBox, QLineEdit,
                            QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
                            QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QTimer, Signal as pyqtSignal, QObject, QThread, QSettings
from PySide6.QtGui import QIcon, QColor, QPixmap

# Busylight
try:
    # Try the import that works with your device
    from busylight.lights import Busylight_Omega
    from busylight.lights.exceptions import LightUnavailable
    USE_OMEGA = True
except ImportError:
    # Fall back to the generic Light class
    from busylight.lights import Light
    from busylight.lights.exceptions import LightUnavailable
    USE_OMEGA = False

from busylight.lights.kuando._busylight import Ring, Instruction, CommandBuffer

# Load environment variables
dotenv.load_dotenv()

def get_timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Configuration dialog class
class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Busylight Configuration")
        self.resize(500, 300)
        
        # Load settings
        self.settings = QSettings("Busylight", "BusylightController")
        
        # Setup UI
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Redis settings group
        redis_group = QGroupBox("Redis Connection Settings")
        redis_layout = QFormLayout(redis_group)
        
        self.redis_host_input = QLineEdit()
        self.redis_port_input = QLineEdit()
        self.redis_token_input = QLineEdit()
        
        # Option to hide token
        self.redis_token_input.setEchoMode(QLineEdit.Password)
        
        # Replace checkbox with a button
        token_layout = QHBoxLayout()
        token_layout.addWidget(self.redis_token_input)
        
        self.show_token_button = QPushButton("👁️")  # Eye emoji
        self.show_token_button.setToolTip("Show/Hide Token")
        self.show_token_button.setFixedWidth(30)
        self.show_token_button.setCheckable(True)
        self.show_token_button.clicked.connect(self.toggle_token_visibility)
        token_layout.addWidget(self.show_token_button)
        
        redis_layout.addRow("Redis Host:", self.redis_host_input)
        redis_layout.addRow("Redis Port:", self.redis_port_input)
        redis_layout.addRow("Redis Bearer Token:", token_layout)
        
        # General settings group
        general_group = QGroupBox("Application Settings")
        general_layout = QFormLayout(general_group)
        
        self.start_minimized_checkbox = QCheckBox()
        self.autostart_checkbox = QCheckBox()
        self.simulation_mode_checkbox = QCheckBox()
        
        general_layout.addRow("Start Minimized:", self.start_minimized_checkbox)
        general_layout.addRow("Run at System Startup:", self.autostart_checkbox)
        general_layout.addRow("Simulation Mode (when no light available):", self.simulation_mode_checkbox)
        
        # Test connection button
        test_button = QPushButton("Test Connection")
        test_button.clicked.connect(self.test_connection)
        
        # Add status label for test results
        self.test_status_label = QLabel()
        self.test_status_label.setAlignment(Qt.AlignCenter)
        
        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Save | 
                                     QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        
        # Add to layout
        layout.addWidget(redis_group)
        layout.addWidget(general_group)
        layout.addWidget(test_button)
        layout.addWidget(self.test_status_label)
        layout.addWidget(button_box)
        
    def load_settings(self):
        # Load and set values
        self.redis_host_input.setText(self.settings.value("redis/host", "busylight.signalwire.me"))
        self.redis_port_input.setText(self.settings.value("redis/port", "6379"))
        
        # Load token from settings or environment
        token = self.settings.value("redis/token", "")
        if not token and os.getenv('REDIS_BEARER_TOKEN'):
            token = os.getenv('REDIS_BEARER_TOKEN')
        self.redis_token_input.setText(token)
        
        # Load app settings
        self.start_minimized_checkbox.setChecked(self.settings.value("app/start_minimized", False, type=bool))
        self.autostart_checkbox.setChecked(self.settings.value("app/autostart", False, type=bool))
        self.simulation_mode_checkbox.setChecked(self.settings.value("app/simulation_mode", True, type=bool))
        
    def save_settings(self):
        # Save Redis settings
        self.settings.setValue("redis/host", self.redis_host_input.text())
        self.settings.setValue("redis/port", self.redis_port_input.text())
        self.settings.setValue("redis/token", self.redis_token_input.text())
        
        # Save app settings
        self.settings.setValue("app/start_minimized", self.start_minimized_checkbox.isChecked())
        self.settings.setValue("app/autostart", self.autostart_checkbox.isChecked())
        self.settings.setValue("app/simulation_mode", self.simulation_mode_checkbox.isChecked())
        
        # Make sure settings are flushed to disk
        self.settings.sync()
        
        # Handle autostart setting
        self.setup_autostart(self.autostart_checkbox.isChecked())
        
        self.accept()
        
    def toggle_token_visibility(self, checked):
        """Toggle the visibility of the token input field"""
        print(f"Toggle token visibility: {checked}")
        if checked:
            print("Setting to Normal mode")
            self.redis_token_input.setEchoMode(QLineEdit.Normal)
        else:
            print("Setting to Password mode")
            self.redis_token_input.setEchoMode(QLineEdit.Password)
            
    def setup_autostart(self, enable):
        """Setup application to run at system startup"""
        # Implementation differs based on operating system
        system = platform.system()
        
        if system == "Darwin":  # macOS
            # For macOS, we'd need to create a LaunchAgent
            # This is simplified and may need adjustment
            app_path = QApplication.applicationFilePath()
            plist_dir = os.path.expanduser("~/Library/LaunchAgents")
            plist_path = os.path.join(plist_dir, "com.busylight.controller.plist")
            
            if enable:
                os.makedirs(plist_dir, exist_ok=True)
                with open(plist_path, "w") as f:
                    f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.busylight.controller</string>
    <key>ProgramArguments</key>
    <array>
        <string>{app_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>""")
            else:
                if os.path.exists(plist_path):
                    os.remove(plist_path)
            
        elif system == "Windows":
            # For Windows, add/remove from the registry
            try:
                # Only import winreg on Windows
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                    if enable:
                        # Get the full path to executable
                        # For PyInstaller, __file__ might not work as expected
                        if getattr(sys, 'frozen', False):
                            # Running as bundled executable
                            app_path = sys.executable
                        else:
                            # Running as script
                            app_path = QApplication.applicationFilePath()
                        
                        # Make sure we have proper backslashes for Windows
                        app_path = app_path.replace('/', '\\')
                        
                        # Add to startup registry
                        winreg.SetValueEx(key, "BusylightController", 0, winreg.REG_SZ, app_path)
                        self.log_message.emit(f"[{get_timestamp()}] Added to Windows startup: {app_path}")
                    else:
                        try:
                            winreg.DeleteValue(key, "BusylightController")
                            self.log_message.emit(f"[{get_timestamp()}] Removed from Windows startup")
                        except FileNotFoundError:
                            pass
            except ImportError:
                self.log_message.emit(f"[{get_timestamp()}] Error: winreg module not available (not running on Windows)")
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error setting up autostart: {e}")
    
    def test_connection(self):
        """Test the Redis connection with current settings without showing dialogs"""
        host = self.redis_host_input.text()
        port = int(self.redis_port_input.text())
        token = self.redis_token_input.text()
        
        # Update status to testing
        self.test_status_label.setText("Testing connection...")
        self.test_status_label.setStyleSheet("color: blue;")
        QApplication.processEvents()
        
        try:
            # Try to get Redis password using token
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            r = requests.get(f'http://{host}/api/status/redis-info', headers=headers, timeout=5)
            data = json.loads(r.text)
            
            if 'password' in data:
                # Try to connect to Redis
                redis_client = redis.StrictRedis(
                    host=host,
                    port=port,
                    password=data['password'],
                    db=0,
                    decode_responses=True            
                )
                
                # Check if Redis connection is successful
                redis_client.ping()
                
                # Update status label with success
                self.test_status_label.setText("Connection successful!")
                self.test_status_label.setStyleSheet("color: green; font-weight: bold;")
            else:
                # Update status label with failure
                error_msg = data.get('error', 'Unknown error')
                self.test_status_label.setText(f"Failed: {error_msg}")
                self.test_status_label.setStyleSheet("color: red; font-weight: bold;")
        except Exception as e:
            # Update status label with error
            self.test_status_label.setText(f"Error: {str(e)}")
            self.test_status_label.setStyleSheet("color: red; font-weight: bold;")
        
        # Clear the status label after a delay
        QTimer.singleShot(3000, lambda: self.test_status_label.setText(""))


# Worker class to handle redis operations in background
class RedisWorker(QObject):
    status_updated = pyqtSignal(str)
    connection_status = pyqtSignal(str)
    log_message = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.redis_client = None
        self.is_running = True
        
        # Load settings
        settings = QSettings("Busylight", "BusylightController")
        self.redis_host = settings.value("redis/host", "busylight.signalwire.me")
        self.redis_port = int(settings.value("redis/port", 6379))
        
        # Get token from settings or environment
        self.redis_bearer_token = settings.value("redis/token", "")
        if not self.redis_bearer_token:
            self.redis_bearer_token = os.getenv('REDIS_BEARER_TOKEN')
        
    def connect_to_redis(self):
        if not self.redis_bearer_token:
            self.log_message.emit(f"[{get_timestamp()}] Error: Redis Bearer Token is not set")
            self.connection_status.emit("disconnected")
            return False
            
        try:
            redis_password = self.get_redis_password()
            self.redis_client = redis.StrictRedis(
                host=self.redis_host,
                port=self.redis_port,
                password=redis_password,
                db=0,
                decode_responses=True            
            )
            
            # Check if Redis connection is successful
            self.redis_client.ping()
            self.log_message.emit(f"[{get_timestamp()}] Connected to Redis successfully")
            self.connection_status.emit("connected")
            return True
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Redis connection error: {e}")
            self.connection_status.emit("disconnected")
            return False
            
    def get_redis_password(self):
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.redis_bearer_token}'
        }
        try:
            r = requests.get(f'http://{self.redis_host}/api/status/redis-info', headers=headers)
            return json.loads(r.text)['password']
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Error getting redis password: {e}")
            raise
            
    def run(self):
        if not self.connect_to_redis():
            return
            
        queue_name = "event_queue"  # historical state of the queue
        queue_channel = "event_channel"  # real time events channel

        # Get the most recent status from redis on startup
        try:
            latest = self.redis_client.lindex(queue_name, -1)
            if latest:
                data = json.loads(latest)
                self.log_message.emit(f"[{get_timestamp()}] Last message: {data}")
                status = data['status']
                self.status_updated.emit(status)
            else:
                self.status_updated.emit('normal')
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Error getting last message: {e}")
        
        # Subscribe to the channel
        pubsub = self.redis_client.pubsub()
        pubsub.subscribe(queue_channel)
        self.log_message.emit(f"[{get_timestamp()}] Subscribed to {queue_channel}")
        self.log_message.emit(f"[{get_timestamp()}] Listening for messages...")
        
        # Listen for messages in a loop
        while self.is_running:
            message = pubsub.get_message(timeout=0.1)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    self.log_message.emit(f"[{get_timestamp()}] Received: {data}")
                    status = data.get('status', 'error')
                    self.status_updated.emit(status)
                except Exception as e:
                    self.log_message.emit(f"[{get_timestamp()}] Error processing message: {e}")
                    self.status_updated.emit('error')
            
            # Small sleep to prevent CPU hogging
            QThread.msleep(100)
            
    def stop(self):
        self.is_running = False
        self.log_message.emit(f"[{get_timestamp()}] Stopping Redis listener")

# Light controller class
class LightController(QObject):
    log_message = pyqtSignal(str)
    color_changed = pyqtSignal(str)
    device_status_changed = pyqtSignal(bool, str)  # Connected, Device name
    
    COLOR_MAP = {
        'alert': (255, 0, 0),
        'alert-acked': (255, 140, 0),
        'warning': (255, 255, 0),
        'error': (255, 0, 255),
        'normal': (0, 255, 0),  # default (renamed from 'default' to 'normal')
        'default': (0, 255, 0), # For backward compatibility with original script
        'off': (0, 0, 0)        # off
    }

    COLOR_NAMES = {
        'alert': "Red (Alert)",
        'alert-acked': "Orange (Alert-Acked)",
        'warning': "Yellow (Warning)",
        'error': "Purple (Error)",
        'normal': "Green (Normal)",
        'off': "Off"
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_status = "off"
        self.light = None
        self.simulation_mode = False
        self.reconnect_timer = None
        self.state_maintenance_timer = None
        
        # Load settings
        settings = QSettings("Busylight", "BusylightController")
        self.allow_simulation = settings.value("app/simulation_mode", True, type=bool)
        
        # Initialize reconnect timer
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.try_connect_device)
        
        # Initialize state maintenance timer to refresh the light state every 30 seconds
        self.state_maintenance_timer = QTimer(self)
        self.state_maintenance_timer.timeout.connect(self.refresh_light_state)
        self.state_maintenance_timer.start(20000)  # 20 second interval
        
        # Initial connection attempt
        self.try_connect_device()
    
    def refresh_light_state(self):
        """Refresh the light state to keep it active"""
        if self.light is not None and self.current_status != "off":
            try:
                # Get current color to check connection
                _ = self.light.color
                
                # Reapply the current status to maintain state, but without logging
                self.set_status(self.current_status, log_action=False)
                
            except Exception:
                # Light may be disconnected, try to reconnect
                self.light = None
                self.log_message.emit(f"[{get_timestamp()}] Lost connection to light during refresh, will try to reconnect...")
                self.try_connect_device()
    
    def try_connect_device(self):
        """Try to connect to the Busylight device"""
        # If we already have a light, no need to reconnect
        if self.light is not None:
            # Check if the light is still working
            try:
                # Try to access a property to see if the light is still responsive
                _ = self.light.color
                # Light is working, make sure status reflects that
                self.device_status_changed.emit(True, self.light.name)
                return  # Light is working, no need to reconnect
            except Exception:
                # Light is not responsive, set to None so we'll try to reconnect
                self.light = None
                self.log_message.emit(f"[{get_timestamp()}] Lost connection to light, will try to reconnect...")
        
        try:
            # Use Busylight_Omega if available, otherwise fall back to Light
            if USE_OMEGA:
                self.light = Busylight_Omega.first_light()
            else:
                self.light = Light.first_light()
                
            self.log_message.emit(f"[{get_timestamp()}] Found light: {self.light.name}")
            
            # If we successfully connected, stop the reconnect timer
            if self.reconnect_timer.isActive():
                self.reconnect_timer.stop()
                
            # If the light was in simulation mode, exit that mode
            if self.simulation_mode:
                self.simulation_mode = False
                self.log_message.emit(f"[{get_timestamp()}] Exited simulation mode, now using physical light")
            
            # Emit device connected signal
            self.device_status_changed.emit(True, self.light.name)
                
            # Apply current status to the newly connected light
            if self.current_status != "off":
                self.set_status(self.current_status)
                
        except LightUnavailable as e:
            if not self.simulation_mode and self.allow_simulation:
                self.simulation_mode = True
                self.log_message.emit(f"[{get_timestamp()}] Device unavailable ({str(e)}). Running in simulation mode.")
            
            # Emit device disconnected signal
            self.device_status_changed.emit(False, "")
            
            # Start the reconnect timer if not already running
            if not self.reconnect_timer.isActive():
                self.reconnect_timer.start(10000)  # Try every 10 seconds
                self.log_message.emit(f"[{get_timestamp()}] Will try to reconnect every 10 seconds")
        
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Error connecting to light: {e}")
            
            if not self.simulation_mode and self.allow_simulation:
                self.simulation_mode = True
                self.log_message.emit(f"[{get_timestamp()}] Running in simulation mode. Status changes will be shown in the UI only.")
            
            # Emit device disconnected signal
            self.device_status_changed.emit(False, "")
            
            # Start the reconnect timer if not already running
            if not self.reconnect_timer.isActive():
                self.reconnect_timer.start(10000)  # Try every 10 seconds
                self.log_message.emit(f"[{get_timestamp()}] Will try to reconnect every 10 seconds")
    
    def set_status(self, status, log_action=True):
        """Set light status with optional logging and UI updates."""
        if not self.light and not self.simulation_mode:
            if log_action:
                self.log_message.emit(f"[{get_timestamp()}] No light device found and simulation mode is disabled")
            return
            
        if status not in self.COLOR_MAP:
            status = 'normal'
            
        self.current_status = status
        color = self.COLOR_MAP[status]
        
        # Always emit color changed signal for UI updates, but only log if requested
        self.color_changed.emit(status)
        
        if log_action:
            self.log_message.emit(f"[{get_timestamp()}] Changing light to {self.COLOR_NAMES[status]}")
        
        # If in simulation mode, just update the UI
        if self.simulation_mode:
            return
        
        # Defaults
        ringtone = Ring.Off
        volume = 0
        
        # Special case for alert status
        if status == 'alert':
            ringtone = Ring.OpenOffice
            volume = 7
        
        try:
            cmd_buffer = CommandBuffer()

            # Create and send the instructions to the light
            instruction = Instruction.Jump(
                ringtone=ringtone,
                volume=volume,
                update=1,
            )

            cmd_buffer.line0 = instruction.value
            command_bytes = bytes(cmd_buffer)

            self.light.write_strategy(command_bytes)
            self.light.on(color)
            self.light.update()
        except Exception as e:
            if log_action:
                self.log_message.emit(f"[{get_timestamp()}] Error controlling light: {e}")
    
    def turn_off(self):
        self.set_status('off')

# Main window class
class BusylightApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Busylight Controller")
        self.setMinimumSize(600, 500)
        
        # For both Mac and Windows - make window not appear in dock/taskbar
        # by setting the window type to a utility/tool window
        self.setWindowFlags(Qt.Tool | Qt.WindowStaysOnTopHint)
        
        # Load settings
        self.settings = QSettings("Busylight", "BusylightController")
        
        # Initialize components
        self.light_controller = LightController()
        self.light_controller.log_message.connect(self.add_log)
        self.light_controller.color_changed.connect(self.update_status_display)
        self.light_controller.device_status_changed.connect(self.update_device_status)
        
        # Setup worker thread for Redis
        self.worker_thread = QThread()
        self.redis_worker = RedisWorker()
        self.redis_worker.moveToThread(self.worker_thread)
        self.redis_worker.log_message.connect(self.add_log)
        self.redis_worker.status_updated.connect(self.light_controller.set_status)
        self.redis_worker.connection_status.connect(self.update_connection_status)
        self.worker_thread.started.connect(self.redis_worker.run)
        
        # Create UI
        self.setup_ui()
        
        # Setup system tray
        self.setup_tray()
        
        # Initialize device status display
        if self.light_controller.light:
            self.update_device_status(True, self.light_controller.light.name)
        elif self.light_controller.simulation_mode:
            self.update_device_status(False, "Simulation Mode")
        else:
            self.update_device_status(False, "")
        
        # Check if we should start minimized
        start_minimized = self.settings.value("app/start_minimized", False, type=bool)
        if start_minimized:
            # Just don't show the window and let the tray icon be the only visible UI
            self.hide()
        else:
            # Show and raise window to ensure visibility
            self.show_and_raise()
        
        # Start worker thread
        self.worker_thread.start()
        
    def setup_ui(self):
        # Main widget and layout
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # Status display
        status_group = QGroupBox("Current Status")
        status_layout = QVBoxLayout(status_group)
        
        self.status_label = QLabel("Status: Off")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        
        self.connection_label = QLabel("Connection: Disconnected")
        self.connection_label.setAlignment(Qt.AlignCenter)
        
        self.device_label = QLabel("Device: Disconnected")
        self.device_label.setAlignment(Qt.AlignCenter)
        self.device_label.setStyleSheet("color: red;")
        
        # Add refresh button for reconnection attempts
        refresh_button = QPushButton("Reconnect Device")
        refresh_button.clicked.connect(self.manually_connect_device)
        
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.connection_label)
        status_layout.addWidget(self.device_label)
        status_layout.addWidget(refresh_button)
        
        # Manual control
        control_group = QGroupBox("Manual Control")
        control_layout = QVBoxLayout(control_group)
        
        self.status_combo = QComboBox()
        for status in self.light_controller.COLOR_NAMES:
            self.status_combo.addItem(self.light_controller.COLOR_NAMES[status], status)
        
        set_status_button = QPushButton("Set Status")
        set_status_button.clicked.connect(self.on_set_status)
        
        # Add configuration button
        config_button = QPushButton("Configuration")
        config_button.clicked.connect(self.show_config_dialog)
        
        control_layout.addWidget(self.status_combo)
        control_layout.addWidget(set_status_button)
        control_layout.addWidget(config_button)
        
        # Log display
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        # Add everything to main layout
        main_layout.addWidget(status_group)
        main_layout.addWidget(control_group)
        main_layout.addWidget(log_group)
        
        self.setCentralWidget(central_widget)
    
    def setup_tray(self):
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set a default icon - create a colored circle based on current status
        self.update_tray_icon(self.light_controller.current_status)
        
        self.tray_icon.setToolTip("Busylight Controller")
        
        # Create context menu for the tray
        tray_menu = QMenu()
        
        # Add status submenu
        status_menu = QMenu("Set Status", tray_menu)
        for status, name in self.light_controller.COLOR_NAMES.items():
            action = status_menu.addAction(name)
            action.setData(status)
            action.triggered.connect(self.on_tray_status_changed)
        
        tray_menu.addMenu(status_menu)
        tray_menu.addSeparator()
        
        # Add config option
        config_action = tray_menu.addAction("Configuration")
        config_action.triggered.connect(self.show_config_dialog)
        
        # Add other actions
        show_action = tray_menu.addAction("Show")
        show_action.triggered.connect(self.show_and_raise)
        
        exit_action = tray_menu.addAction("Exit")
        exit_action.triggered.connect(self.on_exit)
        
        # Set the context menu for the tray
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # Connect the activated signal to show window when icon is clicked
        self.tray_icon.activated.connect(self.on_tray_activated)
    
    def update_tray_icon(self, status):
        """Create and update the tray icon based on current status"""
        if status not in self.light_controller.COLOR_MAP:
            status = 'normal'
            
        # Create a colored icon
        pixmap = QPixmap(22, 22)
        color = self.light_controller.COLOR_MAP[status]
        pixmap.fill(QColor(*color))
        
        # Set the icon
        self.tray_icon.setIcon(QIcon(pixmap))
    
    def show_config_dialog(self):
        """Show the configuration dialog"""
        dialog = ConfigDialog(self)
        if dialog.exec() == QDialog.Accepted:
            # Restart the Redis worker with new settings
            self.restart_worker()
    
    def restart_worker(self):
        """Restart the worker thread with new settings"""
        # Stop current worker
        self.redis_worker.stop()
        self.worker_thread.quit()
        self.worker_thread.wait()
        
        # Create new worker with updated settings
        self.worker_thread = QThread()
        self.redis_worker = RedisWorker()
        self.redis_worker.moveToThread(self.worker_thread)
        self.redis_worker.log_message.connect(self.add_log)
        self.redis_worker.status_updated.connect(self.light_controller.set_status)
        self.redis_worker.connection_status.connect(self.update_connection_status)
        self.worker_thread.started.connect(self.redis_worker.run)
        
        # Start the new worker
        self.add_log(f"[{get_timestamp()}] Restarting Redis connection with new settings")
        self.worker_thread.start()
    
    def on_set_status(self):
        """Set the status of the light directly without confirmation"""
        selected_status = self.status_combo.currentData()
        self.light_controller.set_status(selected_status)
    
    def on_tray_status_changed(self):
        action = self.sender()
        if action:
            status = action.data()
            self.light_controller.set_status(status)
    
    def update_status_display(self, status):
        self.status_label.setText(f"Status: {self.light_controller.COLOR_NAMES.get(status, 'Unknown')}")
        
        # Set the color of the status label background
        if status in self.light_controller.COLOR_MAP:
            r, g, b = self.light_controller.COLOR_MAP[status]
            if status == 'off':
                self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
            else:
                self.status_label.setStyleSheet(f"font-size: 18px; font-weight: bold; background-color: rgb({r}, {g}, {b}); color: black;")
        
        # Update the tray icon
        self.update_tray_icon(status)
    
    def update_connection_status(self, status):
        if status == "connected":
            self.connection_label.setText("Connection: Connected")
            self.connection_label.setStyleSheet("color: green;")
        else:
            self.connection_label.setText("Connection: Disconnected")
            self.connection_label.setStyleSheet("color: red;")
    
    def add_log(self, message):
        self.log_text.append(message)
        # Auto scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def on_exit(self):
        """Safely shut down the application and clean up resources"""
        try:
            # Log exit attempt
            print(f"[{get_timestamp()}] Application exit initiated")
            
            # Stop the reconnect timer if it's running
            if self.light_controller and hasattr(self.light_controller, 'reconnect_timer') and self.light_controller.reconnect_timer.isActive():
                self.light_controller.reconnect_timer.stop()
                print(f"[{get_timestamp()}] Stopped reconnect timer")
            
            # Stop the state maintenance timer if it's running
            if self.light_controller and hasattr(self.light_controller, 'state_maintenance_timer') and self.light_controller.state_maintenance_timer.isActive():
                self.light_controller.state_maintenance_timer.stop()
                print(f"[{get_timestamp()}] Stopped state maintenance timer")
            
            # Stop the worker thread safely
            if hasattr(self, 'redis_worker') and self.redis_worker:
                try:
                    self.redis_worker.stop()
                    print(f"[{get_timestamp()}] Stopped Redis worker")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error stopping Redis worker: {e}")
            
            if hasattr(self, 'worker_thread') and self.worker_thread:
                try:
                    self.worker_thread.quit()
                    # Wait with timeout to prevent hanging
                    if not self.worker_thread.wait(1000):  # 1 second timeout
                        print(f"[{get_timestamp()}] Worker thread did not terminate cleanly, forcing termination")
                        self.worker_thread.terminate()
                    print(f"[{get_timestamp()}] Worker thread stopped")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error stopping worker thread: {e}")
            
            # Turn off the light if possible
            if self.light_controller:
                try:
                    self.light_controller.turn_off()
                    print(f"[{get_timestamp()}] Light turned off")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error turning off light: {e}")
            
            # Remove the tray icon before exit to prevent crashes
            if hasattr(self, 'tray_icon') and self.tray_icon:
                try:
                    self.tray_icon.hide()
                    self.tray_icon.setVisible(False)
                    print(f"[{get_timestamp()}] Tray icon hidden")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error hiding tray icon: {e}")
                
            print(f"[{get_timestamp()}] Application exit complete")
        except Exception as e:
            print(f"[{get_timestamp()}] Error during application exit: {e}")
        finally:
            # Mark application as quitting to allow window to close properly
            QApplication.instance().setProperty("is_quitting", True)
            # Exit the application
            QApplication.quit()
    
    def closeEvent(self, event):
        """Handle window close events"""
        # Check if the application is actually quitting
        if QApplication.instance().property("is_quitting"):
            # Allow the close if the application is quitting
            event.accept()
        else:
            # Hide to tray instead of closing when just the window is closed
            self.hide()
            event.ignore()

    def update_device_status(self, connected, device_name):
        """Update the device status display"""
        self.device_label = getattr(self, 'device_label', None)
        if not self.device_label:
            return
            
        if connected:
            self.device_label.setText(f"Device: {device_name}")
            self.device_label.setStyleSheet("color: green;")
        else:
            if self.light_controller.simulation_mode:
                self.device_label.setText("Device: Simulation Mode")
                self.device_label.setStyleSheet("color: orange;")
            else:
                self.device_label.setText("Device: Disconnected")
                self.device_label.setStyleSheet("color: red;")

    def manually_connect_device(self):
        """Manually attempt to connect to the device with user feedback"""
        # Show a temporary message
        original_text = self.device_label.text()
        original_style = self.device_label.styleSheet()
        self.device_label.setText("Attempting to connect...")
        self.device_label.setStyleSheet("color: blue;")
        
        # Process events to make sure the UI updates
        QApplication.processEvents()
        
        # Log diagnostic information
        self.add_log(f"[{get_timestamp()}] Attempting manual device connection")
        self.add_log(f"[{get_timestamp()}] USE_OMEGA: {USE_OMEGA}")
        
        try:
            # List available devices (if possible)
            if USE_OMEGA:
                devices = Busylight_Omega.available_lights()
            else:
                devices = Light.available_lights()
                
            self.add_log(f"[{get_timestamp()}] Available devices: {len(devices)}")
            for i, device in enumerate(devices):
                self.add_log(f"[{get_timestamp()}]   Device {i+1}: {device}")
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error listing devices: {e}")
        
        # Try to connect
        self.light_controller.try_connect_device()
        
        # If still not connected after the attempt, show a more obvious message
        if not self.light_controller.light and not self.light_controller.simulation_mode:
            self.device_label.setText("Device not found!")
            self.device_label.setStyleSheet("color: red; font-weight: bold;")
            
            # Wait a moment then restore the normal status display
            QTimer.singleShot(2000, lambda: self.update_device_status(
                False, 
                "Simulation Mode" if self.light_controller.simulation_mode else ""
            ))

    def show_and_raise(self):
        """Show and raise the window to the top to make it visible"""
        # Make sure it's visible and on top
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowMinimized) | Qt.WindowActive)
        self.raise_()
        self.activateWindow()

    def on_tray_activated(self, reason):
        """Handle tray icon activation (like double-click)"""
        # Only act on double click or trigger click (varies by platform)
        if reason == QSystemTrayIcon.DoubleClick or reason == QSystemTrayIcon.Trigger:
            self.show_and_raise()

# Main application
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep app running when window is closed
    
    # Create default icon if needed
    create_default_icon()
    
    # Set application icon
    if os.path.exists("icon.png"):
        app_icon = QIcon("icon.png")
    else:
        # Fallback icon (in case saving failed)
        pixmap = QPixmap(64, 64)
        pixmap.fill(QColor(0, 255, 0))  # Default to green
        app_icon = QIcon(pixmap)
    
    # Set app icon    
    app.setWindowIcon(app_icon)
    
    # Platform-specific customizations
    system = platform.system()
    if system == "Darwin":  # macOS
        # On macOS, we need to set this attribute to hide dock icon
        app.setAttribute(Qt.AA_DontUseNativeMenuBar, True)
    
    # For both platforms, this will keep the app running without dock/taskbar icons
    
    # Create main window
    window = BusylightApp()
    
    # Set up proper exit handling
    app.aboutToQuit.connect(lambda: cleanup_application(window))
    
    # Start the application
    return app.exec()

def cleanup_application(window):
    """Ensure application exits cleanly"""
    try:
        # Make sure the window is properly closed
        if window:
            # Call on_exit explicitly for clean shutdown
            window.on_exit()
    except Exception as e:
        print(f"Error during application cleanup: {e}")
    
    # Clear any pending events
    QApplication.processEvents()

def create_default_icon():
    """Create a default icon file if it doesn't exist"""
    if not os.path.exists("icon.png"):
        # Create a simple colored icon
        pixmap = QPixmap(128, 128)
        pixmap.fill(QColor(0, 255, 0))  # Green
        
        # Save it
        pixmap.save("icon.png")
        print(f"[{get_timestamp()}] Created default icon.png") 
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
                            QFileDialog, QMessageBox, QScrollArea, QSizePolicy)
from PySide6.QtCore import Qt, QTimer, Signal as pyqtSignal, QObject, QThread, QSettings
from PySide6.QtGui import QIcon, QColor, QPixmap
import subprocess
import webbrowser

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

# Login dialog class
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("B.L.A.S.S.T. - Login")
        self.setModal(True)
        self.setFixedSize(400, 280)
        
        # Center the dialog on screen
        self.center_on_screen()
        
        # Setup UI
        self.setup_ui()
        
        # Store credentials
        self.username = ""
        self.password = ""
        
    def center_on_screen(self):
        """Center the dialog on the screen"""
        screen = QApplication.primaryScreen().geometry()
        dialog_geometry = self.geometry()
        x = (screen.width() - dialog_geometry.width()) // 2
        y = (screen.height() - dialog_geometry.height()) // 2
        self.move(x, y)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Add logo image
        logo_label = QLabel()
        if os.path.exists("sw.jpeg"):
            pixmap = QPixmap("sw.jpeg")
            # Scale the image to a reasonable size (e.g., 200px wide, maintaining aspect ratio)
            scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        else:
            # If image doesn't exist, show a placeholder or skip
            logo_label.setText("(Logo not found)")
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setStyleSheet("color: gray; font-style: italic;")
            layout.addWidget(logo_label)
        
        # Title label
        title_label = QLabel("Please enter your B.L.A.S.S.T. credentials")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold; margin-bottom: 10px;")
        layout.addWidget(title_label)
        
        # Form layout for credentials
        form_layout = QFormLayout()
        
        # Username input
        self.username_input = QLineEdit()
        #self.username_input.setPlaceholderText("Enter your username")
        form_layout.addRow("Username:", self.username_input)
        
        # Password input with show/hide button - create the layout first
        password_layout = QHBoxLayout()
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        #self.password_input.setPlaceholderText("Enter your password")
        password_layout.addWidget(self.password_input)
        
        self.show_password_button = QPushButton("👁️")
        self.show_password_button.setToolTip("Show/Hide Password")
        self.show_password_button.setFixedWidth(30)
        self.show_password_button.setCheckable(True)
        self.show_password_button.clicked.connect(self.toggle_password_visibility)
        password_layout.addWidget(self.show_password_button)
        
        # Add the password layout directly to the form
        form_layout.addRow("Password:", password_layout)
        
        layout.addLayout(form_layout)
                
        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept_login)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus to username input
        self.username_input.setFocus()
        
        # Allow Enter key to submit
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self.accept_login)
        
    def toggle_password_visibility(self, checked):
        """Toggle the visibility of the password input field"""
        if checked:
            self.password_input.setEchoMode(QLineEdit.Normal)
        else:
            self.password_input.setEchoMode(QLineEdit.Password)
            
    def accept_login(self):
        """Validate and accept the login"""
        username = self.username_input.text().strip()
        password = self.password_input.text()
        
        # Basic validation
        if not username:
            QMessageBox.warning(self, "Login Error", "Please enter a username.")
            self.username_input.setFocus()
            return
            
        if not password:
            QMessageBox.warning(self, "Login Error", "Please enter a password.")
            self.password_input.setFocus()
            return
        
        # Authenticate credentials
        if not self.authenticate(username, password):
            QMessageBox.warning(self, "Login Error", "Invalid username or password.")
            self.password_input.clear()
            self.password_input.setFocus()
            return
        
        # Store credentials
        self.username = username
        self.password = password
        
        # Accept the dialog
        self.accept()
        
    def authenticate(self, username, password):
        headers = {
            "Content-Type": "application/json",
        }

        url = f"https://busylight.signalwire.me/api/status/redis-info"

        response = requests.get(
            url,
            headers=headers,
            auth=(username, password)
        )

        if response.status_code == 200:
            print(response.json())
            self.redis_info = response.json()  # Store the full response
            return True
        else:
            return False
        
    def get_credentials(self):
        """Return the entered credentials"""
        return self.username, self.password, getattr(self, 'redis_info', None)

# Configuration dialog class
class ConfigDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Busylight Configuration")
        self.resize(600, 500)  # Increased height for the new options
        
        # Load settings
        self.settings = QSettings("Busylight", "BusylightController")
        
        # Setup UI
        self.setup_ui()
        self.load_settings()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)

        # Text-to-Speech settings group
        tts_group = QGroupBox("Text-to-Speech Settings")
        tts_layout = QFormLayout(tts_group)
        
        self.tts_enabled_checkbox = QCheckBox()
        self.tts_command_input = QLineEdit()
        
        # Create a layout for command input and test button
        tts_cmd_layout = QHBoxLayout()
        tts_cmd_layout.addWidget(self.tts_command_input)
        
        # Add test button
        self.tts_test_button = QPushButton("Test")
        self.tts_test_button.setToolTip("Test the TTS command")
        self.tts_test_button.clicked.connect(self.test_tts_command)
        tts_cmd_layout.addWidget(self.tts_test_button)
        
        tts_layout.addRow("Enable Text-to-Speech:", self.tts_enabled_checkbox)
        tts_layout.addRow("Command Template:", tts_cmd_layout)
        
        # Add help text
        tts_help = QLabel("Use {summary} as a placeholder for the ticket summary")
        tts_help.setStyleSheet("color: gray; font-style: italic;")
        tts_layout.addRow("", tts_help)
        
        # URL Handler settings group
        url_group = QGroupBox("URL Handler Settings")
        url_layout = QFormLayout(url_group)
        
        self.url_enabled_checkbox = QCheckBox()
        self.url_command_input = QLineEdit()
        
        # Create a layout for command input and test button
        url_cmd_layout = QHBoxLayout()
        url_cmd_layout.addWidget(self.url_command_input)
        
        # Add test button
        self.url_test_button = QPushButton("Test")
        self.url_test_button.setToolTip("Test the URL command")
        self.url_test_button.clicked.connect(self.test_url_command)
        url_cmd_layout.addWidget(self.url_test_button)
        
        url_layout.addRow("Open URLs:", self.url_enabled_checkbox)
        url_layout.addRow("Command Template:", url_cmd_layout)
        
        # Add help text
        url_help = QLabel("Use {url} as a placeholder for the ticket URL")
        url_help.setStyleSheet("color: gray; font-style: italic;")
        url_layout.addRow("", url_help)
        
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
        layout.addWidget(tts_group)
        layout.addWidget(url_group)
        layout.addWidget(general_group)
        layout.addWidget(test_button)
        layout.addWidget(self.test_status_label)
        layout.addWidget(button_box)
        
    def load_settings(self):
        # # Load and set values
        # self.redis_host_input.setText(self.settings.value("redis/host", "busylight.signalwire.me"))
        # self.redis_port_input.setText(self.settings.value("redis/port", "6379"))
        
        # # Load token from settings or environment
        # token = self.settings.value("redis/token", "")
        # if not token and os.getenv('REDIS_BEARER_TOKEN'):
        #     token = os.getenv('REDIS_BEARER_TOKEN')
        # self.redis_token_input.setText(token)
        
        # Load text-to-speech settings
        default_tts_cmd = self.get_default_tts_command()
        self.tts_enabled_checkbox.setChecked(self.settings.value("tts/enabled", False, type=bool))
        self.tts_command_input.setText(self.settings.value("tts/command_template", default_tts_cmd))
        
        # Load URL handler settings
        default_url_cmd = self.get_default_url_command()
        self.url_enabled_checkbox.setChecked(self.settings.value("url/enabled", False, type=bool))
        self.url_command_input.setText(self.settings.value("url/command_template", default_url_cmd))
        
        # Load app settings
        self.start_minimized_checkbox.setChecked(self.settings.value("app/start_minimized", False, type=bool))
        self.autostart_checkbox.setChecked(self.settings.value("app/autostart", False, type=bool))
        self.simulation_mode_checkbox.setChecked(self.settings.value("app/simulation_mode", True, type=bool))
    
    def get_default_tts_command(self):
        """Get the default text-to-speech command for the current platform"""
        system = platform.system()
        if system == "Darwin":  # macOS
            return 'say "{summary}"'
        elif system == "Windows":
            return 'powershell -command "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak(\'{summary}\')"'
        else:  # Linux or other
            return 'echo "{summary}" | festival --tts'  # Basic fallback
    
    def get_default_url_command(self):
        """Get the default URL opening command for the current platform"""
        system = platform.system()
        if system == "Darwin":  # macOS
            return 'open "{url}"'
        elif system == "Windows":
            return 'start "" "{url}"'
        else:  # Linux or other
            return 'xdg-open "{url}"'
            
    def save_settings(self):
        # Save Redis settings
        # self.settings.setValue("redis/host", self.redis_host_input.text())
        # self.settings.setValue("redis/port", self.redis_port_input.text())
        # self.settings.setValue("redis/token", self.redis_token_input.text())
        
        # Save text-to-speech settings
        self.settings.setValue("tts/enabled", self.tts_enabled_checkbox.isChecked())
        self.settings.setValue("tts/command_template", self.tts_command_input.text())
        
        # Save URL handler settings
        self.settings.setValue("url/enabled", self.url_enabled_checkbox.isChecked())
        self.settings.setValue("url/command_template", self.url_command_input.text())
        
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

    def test_tts_command(self):
        """Test the text-to-speech functionality securely"""
        try:
            # Use platform-specific approaches for safer TTS testing
            system = platform.system()
            test_message = "This is a test of the text to speech system"
            
            if system == "Darwin":  # macOS
                # Use macOS say command directly
                subprocess.Popen(["say", test_message], shell=False)
                self.test_status_label.setText("TTS test command sent")
                self.test_status_label.setStyleSheet("color: green;")
            
            elif system == "Windows":
                # Use PowerShell with safer argument passing
                ps_script = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{0}')"
                ps_script = ps_script.format(test_message.replace("'", "''"))  # PowerShell escape single quotes
                subprocess.Popen(["powershell", "-Command", ps_script], shell=False)
                self.test_status_label.setText("TTS test command sent")
                self.test_status_label.setStyleSheet("color: green;")
            
            else:  # Linux and other platforms - attempt to use festival
                # Safer approach for Linux using pipes instead of shell
                process = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE, shell=False)
                process.communicate(test_message.encode())
                self.test_status_label.setText("TTS test command sent")
                self.test_status_label.setStyleSheet("color: green;")
                
        except Exception as e:
            self.test_status_label.setText(f"Error: {str(e)}")
            self.test_status_label.setStyleSheet("color: red;")
            
        # Clear the message after a delay
        QTimer.singleShot(3000, lambda: self.test_status_label.setText(""))
    
    def test_url_command(self):
        """Test the URL opening functionality securely"""
        try:
            # Use the standard webbrowser module which is safer than shell commands
            test_url = "https://www.signalwire.com"
            if webbrowser.open(test_url):
                self.test_status_label.setText("Test URL opened successfully")
                self.test_status_label.setStyleSheet("color: green;")
            else:
                self.test_status_label.setText("Failed to open URL with default browser")
                self.test_status_label.setStyleSheet("color: red;")
        except Exception as e:
            self.test_status_label.setText(f"Error: {str(e)}")
            self.test_status_label.setStyleSheet("color: red;")
            
        # Clear the message after a delay
        QTimer.singleShot(3000, lambda: self.test_status_label.setText(""))
    
    def setup_autostart(self, enable):
        """Setup application to run at system startup with improved security"""
        # Implementation differs based on operating system
        system = platform.system()
        
        if system == "Darwin":  # macOS
            try:
                # For macOS, create a LaunchAgent with proper path validation
                app_path = QApplication.applicationFilePath()
                
                # Validate the application path
                if not os.path.isfile(app_path) or not os.access(app_path, os.X_OK):
                    self.log_message.emit(f"[{get_timestamp()}] Error: Invalid application path for autostart")
                    return
                
                plist_dir = os.path.expanduser("~/Library/LaunchAgents")
                plist_path = os.path.join(plist_dir, "com.busylight.controller.plist")
                
                if enable:
                    os.makedirs(plist_dir, exist_ok=True)
                    
                    # XML template using ElementTree for safer XML generation
                    import xml.etree.ElementTree as ET
                    root = ET.Element("plist", version="1.0")
                    
                    # Create the plist structure
                    dict_element = ET.SubElement(root, "dict")
                    
                    # Label
                    ET.SubElement(dict_element, "key").text = "Label"
                    ET.SubElement(dict_element, "string").text = "com.busylight.controller"
                    
                    # Program arguments
                    ET.SubElement(dict_element, "key").text = "ProgramArguments"
                    array_element = ET.SubElement(dict_element, "array")
                    ET.SubElement(array_element, "string").text = app_path
                    
                    # Run at load
                    ET.SubElement(dict_element, "key").text = "RunAtLoad"
                    ET.SubElement(dict_element, "true")
                    
                    # Create plist XML
                    tree = ET.ElementTree(root)
                    
                    # Add DOCTYPE
                    with open(plist_path, "w") as f:
                        f.write('<?xml version="1.0" encoding="UTF-8"?>\n')
                        f.write('<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n')
                        tree.write(f, encoding='unicode')
                        
                    self.log_message.emit(f"[{get_timestamp()}] Added to macOS startup")
                    
                else:
                    if os.path.exists(plist_path):
                        os.remove(plist_path)
                        self.log_message.emit(f"[{get_timestamp()}] Removed from macOS startup")
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error setting up macOS autostart: {e}")
            
        elif system == "Windows":
            try:
                # Only import winreg on Windows
                import winreg
                key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
                
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_WRITE) as key:
                    if enable:
                        # Get the full path to executable
                        if getattr(sys, 'frozen', False):
                            # Running as bundled executable
                            app_path = sys.executable
                        else:
                            # Running as script
                            app_path = QApplication.applicationFilePath()
                        
                        # Validate the application path
                        if not os.path.isfile(app_path) or not os.access(app_path, os.X_OK):
                            self.log_message.emit(f"[{get_timestamp()}] Error: Invalid application path for autostart")
                            return
                            
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
            # Basic host validation to prevent SSRF
            if not self.validate_redis_host(host):
                self.test_status_label.setText(f"Error: Invalid Redis host")
                self.test_status_label.setStyleSheet("color: red; font-weight: bold;")
                return
            
            # Try to get Redis password using token with HTTPS
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {token}'
            }
            
            url = f'https://{host}/api/status/redis-info'
            r = requests.get(url, headers=headers, timeout=5, verify=True)
            
            # Check for successful response
            if r.status_code != 200:
                self.test_status_label.setText(f"Failed: HTTP {r.status_code}")
                self.test_status_label.setStyleSheet("color: red; font-weight: bold;")
                return
                
            data = r.json()
            
            if 'password' in data:
                # Try to connect to Redis
                redis_client = redis.StrictRedis(
                    host=host,
                    port=port,
                    password=data['password'],
                    db=0,
                    decode_responses=True,
                    socket_timeout=5,
                    socket_connect_timeout=5
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
    
    def validate_redis_host(self, host):
        """Validate Redis host to prevent SSRF attacks"""
        # Basic validation - could be extended with a whitelist approach
        if not host or len(host) < 3:
            return False
            
        # Prevent localhost, private IPs, etc.
        forbidden_patterns = [
            'localhost', '127.', '192.168.', '10.', '172.16.', '172.17.', 
            '172.18.', '172.19.', '172.20.', '172.21.', '172.22.', '172.23.',
            '172.24.', '172.25.', '172.26.', '172.27.', '172.28.', '172.29.',
            '172.30.', '172.31.', '0.0.0.0', 'internal', 'local'
        ]
        
        for pattern in forbidden_patterns:
            if pattern in host.lower():
                return False
                
        return True

# Worker class to handle redis operations in background
class RedisWorker(QObject):
    status_updated = pyqtSignal(str)
    connection_status = pyqtSignal(str)
    log_message = pyqtSignal(str)
    ticket_received = pyqtSignal(dict)  # New signal for ticket information
    group_status_updated = pyqtSignal(str, str, dict)  # group, status, full_data
    
    def __init__(self, redis_info, parent=None):
        super().__init__(parent)
        self.redis_client = None
        self.is_running = True
        
        # Use Redis info from login response
        if redis_info:
            self.redis_host = redis_info['host']  # Use host as-is from API
            self.redis_port = redis_info['port']
            self.redis_password = redis_info['password']  # Could be None
            self.groups = redis_info['groups']
        else:
            # Fallback to default values if no redis_info provided
            self.redis_host = "localhost"
            self.redis_port = 6379
            self.redis_password = None
            self.groups = ["default"]
            
    def connect_to_redis(self):
        try:
            # Log connection attempt details
            self.log_message.emit(f"[{get_timestamp()}] Attempting Redis connection to {self.redis_host}:{self.redis_port}")
            if self.redis_password:
                self.log_message.emit(f"[{get_timestamp()}] Using password authentication (password length: {len(self.redis_password)})")
            else:
                self.log_message.emit(f"[{get_timestamp()}] No password authentication")
            
            # Connect directly with provided credentials
            self.redis_client = redis.StrictRedis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,  # Will be None if no auth required
                db=0,
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=10
            )
            
            # Check if Redis connection is successful
            self.redis_client.ping()
            self.log_message.emit(f"[{get_timestamp()}] Connected to Redis at {self.redis_host}:{self.redis_port}")
            self.connection_status.emit("connected")
            return True
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Redis connection error: {e}")
            self.log_message.emit(f"[{get_timestamp()}] Connection details - Host: {self.redis_host}, Port: {self.redis_port}, Password: {'Yes' if self.redis_password else 'No'}")
            self.connection_status.emit("disconnected")
            return False
            
    def run(self):
        if not self.connect_to_redis():
            return
            
        # Get the most recent status from event_queue for each group
        try:
            latest_status = None
            group_found_status = {}
            
            # Get all events from event_queue and find the most recent for each group
            try:
                # Get all items from the event_queue (most recent is at index -1)
                queue_length = self.redis_client.llen("event_queue")
                if queue_length > 0:
                    self.log_message.emit(f"[{get_timestamp()}] Found {queue_length} events in event_queue")
                    
                    # Check events from most recent to oldest
                    for i in range(queue_length):
                        event_data = self.redis_client.lindex("event_queue", -(i+1))  # Start from most recent
                        if event_data:
                            try:
                                data = json.loads(event_data)
                                event_group = data.get('group')
                                event_status = data.get('status')
                                
                                # If this group hasn't been found yet and this event belongs to one of our groups
                                if event_group in self.groups and event_group not in group_found_status:
                                    group_found_status[event_group] = {
                                        'status': event_status,
                                        'data': data
                                    }
                                    self.log_message.emit(f"[{get_timestamp()}] Found recent event for group '{event_group}': {event_status}")
                                    
                                    # Use first status found as overall status
                                    if latest_status is None:
                                        latest_status = event_status
                                        
                                # Stop if we've found status for all our groups
                                if len(group_found_status) == len(self.groups):
                                    break
                                    
                            except json.JSONDecodeError as e:
                                self.log_message.emit(f"[{get_timestamp()}] Error parsing event data: {e}")
                                continue
                else:
                    self.log_message.emit(f"[{get_timestamp()}] No events found in event_queue")
                    
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error accessing event_queue: {e}")
            
            # Emit status for each group (found status or default to normal)
            for group in self.groups:
                if group in group_found_status:
                    # Found a recent event for this group
                    status = group_found_status[group]['status']
                    data = group_found_status[group]['data']
                    self.group_status_updated.emit(group, status, data)
                    self.process_ticket_info(data)
                else:
                    # No recent event found, default to normal
                    self.log_message.emit(f"[{get_timestamp()}] No recent event found for group '{group}', defaulting to normal")
                    default_data = {'group': group, 'status': 'normal'}
                    self.group_status_updated.emit(group, 'normal', default_data)
            
            # Emit overall status
            if latest_status:
                self.status_updated.emit(latest_status)
            else:
                self.status_updated.emit('normal')
                
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Error getting last message: {e}")
        
        # Subscribe to all group channels
        pubsub = self.redis_client.pubsub()
        for group in self.groups:
            channel_name = f"{group}_channel"
            pubsub.subscribe(channel_name)
            self.log_message.emit(f"[{get_timestamp()}] Subscribed to {channel_name}")
        
        self.log_message.emit(f"[{get_timestamp()}] Listening for messages on {len(self.groups)} channels...")
        
        # Listen for messages in a loop
        while self.is_running:
            message = pubsub.get_message(timeout=0.1)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    channel = message["channel"]
                    # Extract group name from channel (remove '_channel' suffix)
                    group = channel.replace('_channel', '') if channel.endswith('_channel') else channel
                    
                    self.log_message.emit(f"[{get_timestamp()}] Received from {channel}: {data}")
                    status = data.get('status', 'error')
                    
                    # Emit group-specific status
                    self.group_status_updated.emit(group, status, data)
                    
                    # Emit overall status (for backward compatibility and light control)
                    self.status_updated.emit(status)
                    
                    # Process ticket information if available
                    self.process_ticket_info(data)
                except Exception as e:
                    self.log_message.emit(f"[{get_timestamp()}] Error processing message: {e}")
                    self.status_updated.emit('error')
            
            # Small sleep to prevent CPU hogging
            QThread.msleep(100)
    
    def process_ticket_info(self, data):
        """Extract and process ticket information from a message"""
        # Check if this is a ticket message with required fields
        if 'ticket' in data and 'status' in data:
            ticket_info = {
                'ticket': data.get('ticket', ''),
                'summary': data.get('summary', ''),
                'url': data.get('url', '')
            }
            
            # Emit the ticket info for the main app to handle
            if ticket_info['ticket']:
                self.log_message.emit(f"[{get_timestamp()}] Ticket information received: #{ticket_info['ticket']}")
                self.ticket_received.emit(ticket_info)
            
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
        'off': (0, 0, 0),        # off
        # Additional colors
        'blue': (0, 0, 255),     # Blue
        'cyan': (0, 255, 255),   # Cyan
        'magenta': (255, 0, 255), # Magenta
        'pink': (255, 105, 180),  # Pink
        'white': (255, 255, 255)  # White
    }

    COLOR_NAMES = {
        'alert': "Red (Alert)",
        'alert-acked': "Orange (Alert-Acked)",
        'warning': "Yellow (Warning)",
        'error': "Purple (Error)",
        'normal': "Green (Normal)",
        'off': "Off",
        # Additional colors
        'blue': "Blue",
        'cyan': "Cyan",
        'magenta': "Magenta",
        'pink': "Pink",
        'white': "White"
    }
    
    # Dictionary of available effects
    EFFECTS = {
        'none': "Solid Color (No Effect)",
        'blink': "Blink"
    }
    
    # Dictionary of available ringtones
    RINGTONES = {
        'off': Ring.Off,
        'quiet': Ring.Quiet,
        'funky': Ring.Funky
    }
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_status = "off"
        self.light = None
        self.simulation_mode = False
        self.reconnect_timer = None
        self.state_maintenance_timer = None
        self.current_effect = "none"
        self.current_ringtone = "off"
        self.current_volume = 0
        self.effect_timer = None
        self.device_connection_attempted = False
        
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
        
        # Initialize effect timer for blinking and other effects
        self.effect_timer = QTimer(self)
        self.effect_timer.timeout.connect(self.update_effect)
        
        # Explicitly connect and emit initial device status
        QTimer.singleShot(0, self.try_connect_device)
        
        # Track group statuses
        self.group_statuses = {}  # {group: {status, timestamp, data}}
        self.group_widgets = {}   # {group: {widget, status_label, timestamp_label}}
    
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
    
    def update_effect(self):
        """Update the light effect animation based on the current effect"""
        if not self.light or self.simulation_mode or self.current_status == "off":
            return
        
        if self.current_effect == "blink":
            # Toggle the light on and off for blinking effect
            try:
                current_state = self.light.color
                if current_state == (0, 0, 0):  # If light is off
                    color = self.COLOR_MAP[self.current_status]
                    self.light.on(color)
                else:  # If light is on
                    self.light.off()
                self.light.update()
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error updating blink effect: {e}")
    
    def try_connect_device(self):
        """Try to connect to the Busylight device"""
        # Mark that we've attempted connection
        self.device_connection_attempted = True
        
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
                
        except Exception as e:
            # Handle both LightUnavailable and NoLightsFound exceptions
            if not self.simulation_mode and self.allow_simulation:
                self.simulation_mode = True
                self.log_message.emit(f"[{get_timestamp()}] Device unavailable ({str(e)}). Running in simulation mode.")
            
            # Emit device disconnected signal
            self.device_status_changed.emit(False, "")
            
            # Start the reconnect timer if not already running
            if not self.reconnect_timer.isActive():
                self.reconnect_timer.start(10000)  # Try every 10 seconds
                self.log_message.emit(f"[{get_timestamp()}] Will try to reconnect every 10 seconds")
    
    def set_status(self, status, log_action=False):
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
        
        # Set ringtone only if it's explicitly selected (not "off")
        ringtone = Ring.Off
        volume = 0
        
        if self.current_ringtone != "off":
            ringtone = self.RINGTONES.get(self.current_ringtone, Ring.Off)
            volume = self.current_volume
        
        # Special case for alert status - only play sound if we haven't explicitly set a different ringtone
        if status == 'alert' and self.current_ringtone == 'off':
            ringtone = Ring.Funky
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
            
            # Apply the effect if one is set
            if self.current_effect == "none" or status == "off":
                # Stop any running effect timer
                if self.effect_timer.isActive():
                    self.effect_timer.stop()
                # Just set the solid color
                if status == "off":
                    self.light.off()
                else:
                    self.light.on(color)
            elif self.current_effect == "blink":
                # Try to use the light's native blink capability if available
                if hasattr(self.light, 'blink'):
                    try:
                        # Stop any running effect timer
                        if self.effect_timer.isActive():
                            self.effect_timer.stop()
                        # Use native blink functionality
                        self.light.blink(color)
                        self.log_message.emit(f"[{get_timestamp()}] Using light's native blink capability")
                    except Exception as e:
                        self.log_message.emit(f"[{get_timestamp()}] Error using native blink: {e}. Falling back to timer-based blink.")
                        # Fall back to timer blink
                        self.light.on(color)
                        if not self.effect_timer.isActive():
                            self.effect_timer.start(500)  # Blink every 500ms
                else:
                    # Use timer-based blinking
                    self.light.on(color)
                    if not self.effect_timer.isActive():
                        self.effect_timer.start(500)  # Blink every 500ms
                
            self.light.update()
        except Exception as e:
            if log_action:
                self.log_message.emit(f"[{get_timestamp()}] Error controlling light: {e}")
    
    def turn_off(self):
        self.set_status('off')

    def set_effect(self, effect_name, log_action=True):
        """Set the current light effect"""
        if effect_name in self.EFFECTS:
            # Skip if the effect isn't changing
            if self.current_effect == effect_name:
                return
                
            # Stop any running effect timer if changing effects
            if self.effect_timer and self.effect_timer.isActive():
                self.effect_timer.stop()
                
            # Update the current effect
            old_effect = self.current_effect
            self.current_effect = effect_name
            
            if log_action:
                # Log that we're changing the effect
                effect_name_display = self.EFFECTS[effect_name]
                self.log_message.emit(f"[{get_timestamp()}] Changing effect from {self.EFFECTS.get(old_effect, 'None')} to {effect_name_display}")
                
            # Apply the effect with current status if not "none" and the light is on
            if effect_name != "none" and self.current_status != "off":
                self.set_status(self.current_status, log_action=False)
        else:
            self.log_message.emit(f"[{get_timestamp()}] Unknown effect: {effect_name}")
    
    def set_ringtone(self, ringtone_name, volume=5, log_action=True):
        """Set the current ringtone and volume"""
        if ringtone_name in self.RINGTONES:
            previous_ringtone = self.current_ringtone
            previous_volume = self.current_volume
            
            self.current_ringtone = ringtone_name
            self.current_volume = volume
            
            if log_action:
                if ringtone_name == "off":
                    self.log_message.emit(f"[{get_timestamp()}] Turning off ringtone")
                else:
                    self.log_message.emit(f"[{get_timestamp()}] Setting ringtone to {ringtone_name} with volume {volume}")
            
            # Apply the ringtone immediately if the light is on
            if self.light is not None and not self.simulation_mode and self.current_status != "off":
                self.set_status(self.current_status, log_action=False)
        else:
            self.log_message.emit(f"[{get_timestamp()}] Unknown ringtone: {ringtone_name}")

# Main window class
class BusylightApp(QMainWindow):
    def __init__(self, username=None, password=None, redis_info=None):
        super().__init__()
        
        # Store user credentials and Redis info
        self.username = username
        self.password = password
        self.redis_info = redis_info
        
        # Track group statuses
        self.group_statuses = {}  # {group: {status, timestamp, data}}
        self.group_widgets = {}   # {group: {widget, status_label, timestamp_label}}
        
        # Setup window title and icon
        self.setWindowTitle("Busylight Controller")
        self.setWindowIcon(QIcon("icon.png"))
        
        # Initialize blinking variables
        self.tray_blink_timer = QTimer(self)
        self.tray_blink_timer.timeout.connect(self.toggle_tray_icon)
        self.tray_icon_visible = True
        
        # Create the light controller first
        self.light_controller = LightController()
        
        # Create UI after controller exists
        self.create_main_ui()
        
        # Setup system tray
        self.setup_tray()
        
        # Set up connections to UI after both UI and controller exist
        self.light_controller.log_message.connect(self.add_log)
        self.light_controller.color_changed.connect(self.update_status_display)
        self.light_controller.device_status_changed.connect(self.update_device_status)
        
        # Create Redis worker thread with Redis info from login
        self.worker_thread = QThread()
        self.redis_worker = RedisWorker(redis_info=self.redis_info)
        self.redis_worker.moveToThread(self.worker_thread)
        self.redis_worker.status_updated.connect(self.light_controller.set_status)
        self.redis_worker.connection_status.connect(self.update_redis_connection_status)
        self.redis_worker.log_message.connect(self.add_log)
        self.redis_worker.ticket_received.connect(self.process_ticket_info)
        self.redis_worker.group_status_updated.connect(self.update_group_status)
        self.worker_thread.started.connect(self.redis_worker.run)
        self.worker_thread.start()
        
        # Explicitly refresh connection on startup after UI is ready
        QTimer.singleShot(100, self.manually_connect_device)
        
    def create_main_ui(self):
        """Create the main UI components with dynamic group status displays"""
        main_widget = QWidget()
        layout = QVBoxLayout()
        
        # User info section
        user_group = QGroupBox("User Information")
        user_layout = QVBoxLayout()
        
        if self.username:
            self.user_label = QLabel(f"Logged in as: {self.username}")
            self.user_label.setStyleSheet("color: blue; font-style: italic; font-size: 14px;")
            self.user_label.setAlignment(Qt.AlignCenter)
            user_layout.addWidget(self.user_label)
        
        # Device info
        self.device_label = QLabel("Device: Disconnected")
        self.device_label.setStyleSheet("color: red;")
        self.device_label.setAlignment(Qt.AlignCenter)
        user_layout.addWidget(self.device_label)
        
        # Redis connection info
        self.redis_connection_label = QLabel("Redis: Disconnected")
        self.redis_connection_label.setStyleSheet("color: red;")
        self.redis_connection_label.setAlignment(Qt.AlignCenter)
        user_layout.addWidget(self.redis_connection_label)
        
        user_group.setLayout(user_layout)
        layout.addWidget(user_group)
        
        # Dynamic Group Status Section
        if self.redis_info and 'groups' in self.redis_info:
            groups_group = QGroupBox("Group Status Monitor")
            groups_layout = QVBoxLayout()
            
            # Create a scrollable area for groups
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_widget = QWidget()
            scroll_layout = QVBoxLayout(scroll_widget)
            
            # Create status widget for each group
            for group in self.redis_info['groups']:
                group_widget = QGroupBox(f"Group: {group}")
                group_layout = QVBoxLayout()
                
                # Status display
                status_label = QLabel("Status: Unknown")
                status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
                status_label.setAlignment(Qt.AlignCenter)
                group_layout.addWidget(status_label)
                
                # Timestamp display
                timestamp_label = QLabel("Last Update: Never")
                timestamp_label.setStyleSheet("color: gray; font-size: 10px; font-style: italic;")
                timestamp_label.setAlignment(Qt.AlignCenter)
                group_layout.addWidget(timestamp_label)
                
                group_widget.setLayout(group_layout)
                scroll_layout.addWidget(group_widget)
                
                # Store references for updates
                self.group_widgets[group] = {
                    'widget': group_widget,
                    'status_label': status_label,
                    'timestamp_label': timestamp_label
                }
            
            scroll_area.setWidget(scroll_widget)
            groups_layout.addWidget(scroll_area)
            groups_group.setLayout(groups_layout)
            layout.addWidget(groups_group)
        else:
            # Fallback single status display if no groups
            status_group = QGroupBox("Status")
            status_layout = QVBoxLayout()
            
            self.status_label = QLabel("Status: Off")
            self.status_label.setStyleSheet("font-size: 18px; font-weight: bold;")
            self.status_label.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(self.status_label)
            
            status_group.setLayout(status_layout)
            layout.addWidget(status_group)
        
        # Log section
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)
        
        # Set window size
        self.resize(900, 800)
        
        # Set up connections
        self.light_controller.log_message.connect(self.add_log)
        self.light_controller.color_changed.connect(self.update_status_display)
        self.light_controller.device_status_changed.connect(self.update_device_status)
    
    def setup_tray(self):
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set a default icon - create a colored circle based on current status
        self.update_tray_icon(self.light_controller.current_status)
        
        self.tray_icon.setToolTip("Busylight Controller")
        
        # Create context menu for the tray
        tray_menu = QMenu()
        
        # Add Light Control submenu
        light_control_menu = QMenu("Light Control", tray_menu)
        
        # Add status submenu
        status_menu = QMenu("Set Status", light_control_menu)
        for status, name in self.light_controller.COLOR_NAMES.items():
            action = status_menu.addAction(name)
            action.setData(status)
            action.triggered.connect(self.on_tray_status_changed)
        light_control_menu.addMenu(status_menu)
        
        # Add effects submenu
        effects_menu = QMenu("Set Effect", light_control_menu)
        for effect, name in self.light_controller.EFFECTS.items():
            action = effects_menu.addAction(name)
            action.setData(effect)
            action.triggered.connect(self.on_tray_effect_changed)
        light_control_menu.addMenu(effects_menu)
        
        # Add ringtones submenu
        ringtones_menu = QMenu("Set Ringtone", light_control_menu)
        # Add Off option first
        off_action = ringtones_menu.addAction("Off")
        off_action.setData(("off", 0))
        off_action.triggered.connect(self.on_tray_ringtone_changed)
        
        # Add separator
        ringtones_menu.addSeparator()
        
        # Add other ringtones with volume levels
        for ringtone in self.light_controller.RINGTONES.keys():
            if ringtone != "off":
                ringtone_submenu = QMenu(ringtone.capitalize(), ringtones_menu)
                for volume in range(1, 11):  # Volume 1-10
                    volume_action = ringtone_submenu.addAction(f"Volume {volume}")
                    volume_action.setData((ringtone, volume))
                    volume_action.triggered.connect(self.on_tray_ringtone_changed)
                ringtones_menu.addMenu(ringtone_submenu)
        light_control_menu.addMenu(ringtones_menu)
        
        # Add separator in light control menu
        light_control_menu.addSeparator()
        
        # Add direct control actions
        turn_off_action = light_control_menu.addAction("Turn Off")
        turn_off_action.triggered.connect(self.light_controller.turn_off)
        
        refresh_connection_action = light_control_menu.addAction("Refresh Connection")
        refresh_connection_action.triggered.connect(self.manually_connect_device)
        
        refresh_status_action = light_control_menu.addAction("Refresh From Redis")
        refresh_status_action.triggered.connect(self.refresh_status_from_redis)
        
        # Add the Light Control menu to main tray menu
        tray_menu.addMenu(light_control_menu)
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
        
        # Handle blinking effect
        if self.light_controller.current_effect == 'blink' and status != 'off':
            # Start tray blinking if not already blinking
            if not self.tray_blink_timer.isActive():
                self.tray_blink_timer.start(500)  # Blink every 500ms
                
            # If we're in the "off" phase of blinking, use black
            if not self.tray_icon_visible:
                # Create a blank icon
                pixmap = QPixmap(22, 22)
                pixmap.fill(QColor(0, 0, 0))
                self.tray_icon.setIcon(QIcon(pixmap))
                return
        else:
            # Stop tray blinking if it was active
            if self.tray_blink_timer.isActive():
                self.tray_blink_timer.stop()
                self.tray_icon_visible = True
            
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
        self.redis_worker = RedisWorker(redis_info=self.redis_info)
        self.redis_worker.moveToThread(self.worker_thread)
        self.redis_worker.log_message.connect(self.add_log)
        self.redis_worker.status_updated.connect(self.light_controller.set_status)
        self.redis_worker.connection_status.connect(self.update_redis_connection_status)
        self.redis_worker.ticket_received.connect(self.process_ticket_info)
        self.redis_worker.group_status_updated.connect(self.update_group_status)
        self.worker_thread.started.connect(self.redis_worker.run)
        
        # Start the new worker
        self.add_log(f"[{get_timestamp()}] Restarting Redis connection with new settings")
        self.worker_thread.start()
    
    def on_tray_status_changed(self):
        action = self.sender()
        if action:
            status = action.data()
            # Use the current effect and ringtone settings when changing from tray
            self.light_controller.set_status(status)
    
    def on_tray_effect_changed(self):
        """Handle effect change from tray menu"""
        action = self.sender()
        if action:
            effect = action.data()
            self.light_controller.set_effect(effect)
            self.add_log(f"[{get_timestamp()}] Effect changed from tray: {self.light_controller.EFFECTS.get(effect, 'Unknown')}")
    
    def on_tray_ringtone_changed(self):
        """Handle ringtone change from tray menu"""
        action = self.sender()
        if action:
            ringtone_data = action.data()
            if isinstance(ringtone_data, tuple):
                ringtone, volume = ringtone_data
                self.light_controller.set_ringtone(ringtone, volume)
                if ringtone == "off":
                    self.add_log(f"[{get_timestamp()}] Ringtone turned off from tray")
                else:
                    self.add_log(f"[{get_timestamp()}] Ringtone changed from tray: {ringtone} volume {volume}")
    
    def update_status_display(self, status):
        # Update the tray icon
        self.update_tray_icon(status)
    
    def add_log(self, message):
        """Add a message to the log if the UI has been created"""
        if not hasattr(self, 'log_text') or self.log_text is None:
            # Just print to console if the UI hasn't been created yet
            print(message)
            return
            
        self.log_text.append(message)
        # Auto scroll to bottom
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def on_exit(self):
        """Safely shut down the application and clean up resources"""
        try:
            # Log exit attempt
            print(f"[{get_timestamp()}] Application exit initiated")
            
            # Stop the tray blink timer if it's running
            if hasattr(self, 'tray_blink_timer') and self.tray_blink_timer.isActive():
                self.tray_blink_timer.stop()
                print(f"[{get_timestamp()}] Stopped tray blink timer")
                
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
        # Ensure the device_label exists
        if not hasattr(self, 'device_label') or not self.device_label:
            return
            
        if connected:
            self.device_label.setText(f"Device: {device_name}")
            self.device_label.setStyleSheet("color: green;")
            self.add_log(f"[{get_timestamp()}] Connected to device: {device_name}")
        else:
            if self.light_controller.simulation_mode:
                self.device_label.setText("Device: Simulation Mode")
                self.device_label.setStyleSheet("color: orange;")
                self.add_log(f"[{get_timestamp()}] Running in simulation mode")
            else:
                self.device_label.setText("Device: Disconnected")
                self.device_label.setStyleSheet("color: red;")
                self.add_log(f"[{get_timestamp()}] Device disconnected")

    def manually_connect_device(self):
        """Manually attempt to connect to the device with user feedback"""
        # Check if the UI has been created already
        if not hasattr(self, 'device_label') or self.device_label is None:
            # Just attempt connection without UI feedback
            self.light_controller.try_connect_device()
            return
            
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
        
        # After connecting, try to retrieve the last status from Redis
        self.refresh_status_from_redis()
        
        # If still not connected after the attempt, show a more obvious message
        if not self.light_controller.light and not self.light_controller.simulation_mode:
            self.device_label.setText("Device not found!")
            self.device_label.setStyleSheet("color: red; font-weight: bold;")
            
            # Wait a moment then restore the normal status display
            QTimer.singleShot(2000, lambda: self.update_device_status(
                False, 
                "Simulation Mode" if self.light_controller.simulation_mode else ""
            ))
            
    def refresh_status_from_redis(self):
        """Retrieve the last status from Redis and apply it"""
        try:
            # Check if Redis worker exists and is connected
            if not hasattr(self, 'redis_worker') or not hasattr(self.redis_worker, 'redis_client') or self.redis_worker.redis_client is None:
                self.add_log(f"[{get_timestamp()}] Cannot refresh from Redis: Redis not connected")
                return
                
            # Try to get the most recent status from any group queue
            for group in self.redis_worker.groups:
                queue_name = f"{group}_channel"
                try:
                    latest = self.redis_worker.redis_client.lindex(queue_name, -1)
                    if latest:
                        try:
                            data = json.loads(latest)
                            status = data.get('status')
                            if status:
                                self.add_log(f"[{get_timestamp()}] Retrieved last status from Redis ({group}): {status}")
                                # Apply the status
                                self.light_controller.set_status(status)
                                return  # Use the first status found
                        except Exception as e:
                            self.add_log(f"[{get_timestamp()}] Error parsing Redis message from {group}: {e}")
                except Exception as e:
                    self.add_log(f"[{get_timestamp()}] Error accessing queue {queue_name}: {e}")
            
            # If we get here, no messages were found in any queue
            self.add_log(f"[{get_timestamp()}] No messages found in any Redis queue")
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error retrieving status from Redis: {e}")

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

    def update_redis_connection_status(self, status):
        """Update the Redis connection status in the UI and log"""
        if hasattr(self, 'redis_connection_label'):
            if status == "connected":
                self.redis_connection_label.setText("Connected")
                self.redis_connection_label.setStyleSheet("color: green;")
                self.add_log(f"[{get_timestamp()}] Redis connected")
            else:
                self.redis_connection_label.setText("Disconnected")
                self.redis_connection_label.setStyleSheet("color: red;")
                self.add_log(f"[{get_timestamp()}] Redis disconnected")

    def toggle_tray_icon(self):
        """Toggle the tray icon visibility"""
        self.tray_icon_visible = not self.tray_icon_visible
        self.update_tray_icon(self.light_controller.current_status)

    def process_ticket_info(self, ticket_info):
        """Process ticket information received from Redis"""
        # Log the ticket information
        ticket_id = ticket_info.get('ticket', 'Unknown')
        summary = ticket_info.get('summary', '')
        url = ticket_info.get('url', '')
        
        self.add_log(f"[{get_timestamp()}] Ticket #{ticket_id} received")
        
        if summary:
            self.add_log(f"[{get_timestamp()}] Summary: {summary}")
            # Handle text-to-speech if enabled
            self.speak_ticket_summary(summary)
            
        if url:
            self.add_log(f"[{get_timestamp()}] URL: {url}")
            # Handle URL opening if enabled
            self.open_ticket_url(url)
    
    def speak_ticket_summary(self, summary):
        """Speak the ticket summary using the configured command"""
        # Load TTS settings
        settings = QSettings("Busylight", "BusylightController")
        tts_enabled = settings.value("tts/enabled", False, type=bool)
        
        if not tts_enabled:
            return
            
        # Get the command template
        tts_cmd_template = settings.value("tts/command_template", "")
        if not tts_cmd_template:
            self.add_log(f"[{get_timestamp()}] Warning: TTS enabled but no command template configured")
            return
        
        try:
            # Use platform-specific approaches for safer TTS
            system = platform.system()
            
            if system == "Darwin":  # macOS
                # Use macOS say command directly with list arguments
                subprocess.Popen(["say", summary], shell=False)
                self.add_log(f"[{get_timestamp()}] Speaking ticket summary using macOS say command")
            
            elif system == "Windows":
                # Use PowerShell with safer argument passing
                ps_script = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{0}')"
                ps_script = ps_script.format(summary.replace("'", "''"))  # PowerShell escape single quotes
                subprocess.Popen(["powershell", "-Command", ps_script], shell=False)
                self.add_log(f"[{get_timestamp()}] Speaking ticket summary using Windows speech")
            
            else:  # Linux and other platforms - attempt to use festival
                # Safer approach for Linux using pipes instead of shell
                process = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE, shell=False)
                process.communicate(summary.encode())
                self.add_log(f"[{get_timestamp()}] Speaking ticket summary using festival")
                
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error executing TTS command: {e}")
    
    def open_ticket_url(self, url):
        """Open the ticket URL using a secure method"""
        # Load URL settings
        settings = QSettings("Busylight", "BusylightController")
        url_enabled = settings.value("url/enabled", False, type=bool)
        
        if not url_enabled:
            return
            
        # Basic URL validation
        if not url.startswith(('http://', 'https://')):
            self.add_log(f"[{get_timestamp()}] Warning: Invalid URL format: {url}")
            return
            
        try:
            # Use the standard webbrowser module which is safer than shell commands
            if webbrowser.open(url):
                self.add_log(f"[{get_timestamp()}] Opening ticket URL safely using webbrowser module")
            else:
                self.add_log(f"[{get_timestamp()}] Failed to open URL with default browser")
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error opening URL: {e}")

    def update_group_status(self, group, status, data):
        """Handle group status updates"""
        self.group_statuses[group] = {
            'status': status,
            'timestamp': get_timestamp(),
            'data': data
        }
        
        # Update the UI widget for this group
        if group in self.group_widgets:
            widgets = self.group_widgets[group]
            status_label = widgets['status_label']
            timestamp_label = widgets['timestamp_label']
            
            # Update status text and color
            status_name = self.light_controller.COLOR_NAMES.get(status, status.title())
            status_label.setText(f"Status: {status_name}")
            
            # Set background color based on status
            if status in self.light_controller.COLOR_MAP:
                r, g, b = self.light_controller.COLOR_MAP[status]
                if status == 'off':
                    status_label.setStyleSheet("font-size: 14px; font-weight: bold; padding: 5px;")
                else:
                    status_label.setStyleSheet(f"font-size: 14px; font-weight: bold; padding: 5px; background-color: rgb({r}, {g}, {b}); color: black;")
            
            # Update timestamp
            timestamp_label.setText(f"Last Update: {get_timestamp()}")
            
            # Log the update
            self.add_log(f"[{get_timestamp()}] Group '{group}' status updated: {status_name}")
            
            # If there's ticket info, log it
            if 'ticket' in data:
                ticket_id = data.get('ticket', 'Unknown')
                summary = data.get('summary', '')
                self.add_log(f"[{get_timestamp()}] Group '{group}' ticket: #{ticket_id} - {summary}")
        else:
            self.add_log(f"[{get_timestamp()}] Group '{group}' status updated: {status} (no UI widget found)")

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
    
    # Show login dialog first
    login_dialog = LoginDialog()
    if login_dialog.exec() != QDialog.Accepted:
        # User cancelled login, exit application
        print(f"[{get_timestamp()}] Login cancelled by user")
        return 0
    
    # Get credentials from login dialog
    username, password, redis_info = login_dialog.get_credentials()
    print(f"[{get_timestamp()}] User '{username}' logged in successfully")
    
    # Create main window with credentials
    window = BusylightApp(username, password, redis_info)
    
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

if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print(f"\n[{get_timestamp()}] Application interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"[{get_timestamp()}] Unexpected error: {e}")
        sys.exit(1) 
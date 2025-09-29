#!/usr/bin/env python3
# Author: Shane Harrell (GUI by Assistant)

import json
import sys
import os
import platform
import argparse
from datetime import datetime
import redis
import asyncio
import requests
import dotenv
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QLabel, QPushButton, QComboBox, QSystemTrayIcon,
                            QMenu, QTextEdit, QHBoxLayout, QGroupBox, QLineEdit,
                            QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
                            QFileDialog, QMessageBox, QScrollArea, QSizePolicy, QTabWidget, QGridLayout)
from PySide6.QtCore import Qt, QTimer, Signal as pyqtSignal, QObject, QThread, QSettings, QRect, QPoint
from PySide6.QtGui import QIcon, QColor, QPixmap, QFont, QPainter, QPen
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

def get_resource_path(relative_path):
    """Get the absolute path to a resource file, works for dev and PyInstaller bundle"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # When running in development, use the current directory
        base_path = os.path.abspath(".")
    
    return os.path.join(base_path, relative_path)

def is_dark_mode():
    """Detect if the system is in dark mode"""
    try:
        # Check Qt's palette to determine if we're in dark mode
        app = QApplication.instance()
        if app:
            palette = app.palette()
            window_color = palette.color(palette.Window)
            # If the window background is dark (sum of RGB < 384), we're in dark mode
            return (window_color.red() + window_color.green() + window_color.blue()) < 384
    except:
        pass
    return False

def get_adaptive_colors():
    """Get colors that adapt to dark/light mode"""
    if is_dark_mode():
        return {
            'bg_primary': '#2b2b2b',
            'bg_secondary': '#3c3c3c', 
            'bg_tertiary': '#4a4a4a',
            'text_primary': '#ffffff',
            'text_secondary': '#b0b0b0',
            'text_muted': '#888888',
            'border_primary': '#555555',
            'border_secondary': '#666666',
            'accent_blue': '#4a9eff',
            'accent_green': '#4caf50',
            'accent_red': '#f44336',
            'accent_orange': '#ff9800',
            'input_bg': '#404040',
            'input_border': '#606060',
            'button_bg': '#505050',
            'hover_bg': '#606060'
        }
    else:
        return {
            'bg_primary': '#ffffff',
            'bg_secondary': '#f8f9fa',
            'bg_tertiary': '#e9ecef',
            'text_primary': '#202124',
            'text_secondary': '#495057',
            'text_muted': '#6c757d',
            'border_primary': '#000000',
            'border_secondary': '#dee2e6',
            'accent_blue': '#4285f4',
            'accent_green': '#28a745',
            'accent_red': '#dc3545',
            'accent_orange': '#fd7e14',
            'input_bg': '#ffffff',
            'input_border': '#e9ecef',
            'button_bg': '#f8f9fa',
            'hover_bg': '#f1f3f4'
        }

# Login dialog class
class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("B.L.A.S.S.T. - Login")
        self.setModal(True)
        self.setFixedSize(400, 280)
        
        # Center the dialog on screen
        self.center_on_screen()
        
        # Initialize QSettings for credential storage
        self.settings = QSettings("Busylight", "BusylightController")
        
        # Setup UI
        self.setup_ui()
        
        # Load saved credentials
        self.load_saved_credentials()
        
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
        
        # Get adaptive colors for styling
        colors = get_adaptive_colors()
        
        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QWidget {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QLabel {{
                color: {colors['text_primary']};
            }}
            QLineEdit {{
                background-color: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                border-radius: 4px;
                padding: 8px;
                color: {colors['text_primary']};
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
            }}
            QPushButton {{
                background-color: {colors['button_bg']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                padding: 6px 12px;
                color: {colors['text_primary']};
            }}
            QPushButton:hover {{
                background-color: {colors['hover_bg']};
            }}
            QDialogButtonBox QPushButton {{
                background-color: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: 500;
                min-width: 80px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background-color: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)

        # Add logo image
        logo_label = QLabel()
        logo_path = get_resource_path("sw.jpeg")
        if os.path.exists(logo_path):
            pixmap = QPixmap(logo_path)
            # Scale the image to a reasonable size (e.g., 200px wide, maintaining aspect ratio)
            scaled_pixmap = pixmap.scaled(200, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)
        else:
            # If image doesn't exist, show a placeholder or skip
            logo_label.setText("(Logo not found)")
            logo_label.setAlignment(Qt.AlignCenter)
            logo_label.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic;")
            layout.addWidget(logo_label)
        
        # Title label
        title_label = QLabel("Please enter your B.L.A.S.S.T. credentials")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"font-weight: bold; margin-bottom: 10px; color: {colors['text_primary']};")
        layout.addWidget(title_label)
        
        # Form layout for credentials
        form_layout = QFormLayout()
        
        # Username input
        self.username_input = QLineEdit()
        #self.username_input.setPlaceholderText("Enter your username")
        
        username_label = QLabel("Username:")
        username_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 500;")
        form_layout.addRow(username_label, self.username_input)
        
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
        password_label = QLabel("Password:")
        password_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 500;")
        form_layout.addRow(password_label, password_layout)
        
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
        
        # Save username for future logins (password is not saved for security)
        self.save_credentials(username)
        
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
            self.redis_info = response.json()  # Store the full response
            return True
        else:
            return False
        
    def get_credentials(self):
        """Return the entered credentials"""
        return self.username, self.password, getattr(self, 'redis_info', None)
    
    def load_saved_credentials(self):
        """Load previously saved credentials if they exist"""
        try:
            # Load saved username
            saved_username = self.settings.value("credentials/username", "")
            if saved_username:
                self.username_input.setText(saved_username)
                # If username exists, focus on password field
                self.password_input.setFocus()
                print(f"[{get_timestamp()}] Loaded saved username: {saved_username}")
            
            # Note: We don't save passwords for security reasons
            # Users will need to re-enter their password each time
            
        except Exception as e:
            print(f"[{get_timestamp()}] Error loading saved credentials: {e}")
    
    def save_credentials(self, username):
        """Save credentials to settings (username only for security)"""
        try:
            # Only save username for convenience, never save passwords
            self.settings.setValue("credentials/username", username)
            self.settings.sync()
            print(f"[{get_timestamp()}] Username saved for future logins")
        except Exception as e:
            print(f"[{get_timestamp()}] Error saving credentials: {e}")
    
    def clear_saved_credentials(self):
        """Clear saved credentials from settings"""
        try:
            self.settings.remove("credentials/username")
            self.settings.sync()
            print(f"[{get_timestamp()}] Saved credentials cleared")
        except Exception as e:
            print(f"[{get_timestamp()}] Error clearing credentials: {e}")

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
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Get adaptive colors for styling
        colors = get_adaptive_colors()
        
        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QWidget {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Text-to-Speech settings group
        tts_group = QGroupBox("Text-to-Speech Settings")
        
        # Set bold font for the title
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(12)
        tts_group.setFont(bold_font)
        
        tts_group.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        
        tts_layout = QFormLayout(tts_group)
        tts_layout.setSpacing(12)
        
        self.tts_enabled_checkbox = QCheckBox()
        self.tts_enabled_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 14px;
                color: {colors['text_primary']};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['input_bg']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['accent_blue']};
                border-color: {colors['accent_blue']};
            }}
        """)
        
        self.tts_command_input = QLineEdit()
        self.tts_command_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
                outline: none;
            }}
        """)
        
        # Create a layout for command input and test button
        tts_cmd_layout = QHBoxLayout()
        tts_cmd_layout.addWidget(self.tts_command_input)
        
        # Add test button
        self.tts_test_button = QPushButton("Test")
        self.tts_test_button.setToolTip("Test the TTS command")
        self.tts_test_button.clicked.connect(self.test_tts_command)
        self.tts_test_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
            QPushButton:pressed {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
        """)
        tts_cmd_layout.addWidget(self.tts_test_button)
        
        tts_layout.addRow("Enable Text-to-Speech:", self.tts_enabled_checkbox)
        tts_layout.addRow("Command Template:", tts_cmd_layout)
        
        # Add help text
        tts_help = QLabel("Use {summary} as a placeholder for the ticket summary")
        tts_help.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic; font-size: 12px; padding: 4px 0;")
        tts_layout.addRow("", tts_help)
        
        # URL Handler settings group
        url_group = QGroupBox("URL Handler Settings")
        
        # Set bold font for the title
        url_group.setFont(bold_font)
        
        url_group.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        
        url_layout = QFormLayout(url_group)
        url_layout.setSpacing(12)
        
        self.url_enabled_checkbox = QCheckBox()
        self.url_enabled_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 14px;
                color: {colors['text_primary']};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['input_bg']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['accent_blue']};
                border-color: {colors['accent_blue']};
            }}
        """)
        
        self.url_command_input = QLineEdit()
        self.url_command_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
                outline: none;
            }}
        """)
        
        # Create a layout for command input and test button
        url_cmd_layout = QHBoxLayout()
        url_cmd_layout.addWidget(self.url_command_input)
        
        # Add test button
        self.url_test_button = QPushButton("Test")
        self.url_test_button.setToolTip("Test the URL command")
        self.url_test_button.clicked.connect(self.test_url_command)
        self.url_test_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
            QPushButton:pressed {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
        """)
        url_cmd_layout.addWidget(self.url_test_button)
        
        url_layout.addRow("Open URLs:", self.url_enabled_checkbox)
        url_layout.addRow("Command Template:", url_cmd_layout)
        
        # Add help text
        url_help = QLabel("Use {url} as a placeholder for the ticket URL")
        url_help.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic; font-size: 12px; padding: 4px 0;")
        url_layout.addRow("", url_help)
        
        # General settings group
        general_group = QGroupBox("Application Settings")
        
        # Set bold font for the title
        general_group.setFont(bold_font)
        
        general_group.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        
        general_layout = QFormLayout(general_group)
        general_layout.setSpacing(12)
        
        # Common checkbox style
        checkbox_style = f"""
            QCheckBox {{
                font-size: 14px;
                color: {colors['text_primary']};
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['input_bg']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['accent_blue']};
                border-color: {colors['accent_blue']};
            }}
        """
        
        self.start_minimized_checkbox = QCheckBox()
        self.start_minimized_checkbox.setStyleSheet(checkbox_style)
        
        self.autostart_checkbox = QCheckBox()
        self.autostart_checkbox.setStyleSheet(checkbox_style)
        
        self.simulation_mode_checkbox = QCheckBox()
        self.simulation_mode_checkbox.setStyleSheet(checkbox_style)
        
        general_layout.addRow("Start Minimized:", self.start_minimized_checkbox)
        general_layout.addRow("Run at System Startup:", self.autostart_checkbox)
        general_layout.addRow("Simulation Mode (when no light available):", self.simulation_mode_checkbox)
        
        # Test connection button
        test_button = QPushButton("Test Connection")
        test_button.clicked.connect(self.test_connection)
        test_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_green']};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 8px;
                font-weight: 600;
                font-size: 14px;
                margin: 8px 0;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
            QPushButton:pressed {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
        """)
        
        # Add status label for test results
        self.test_status_label = QLabel()
        self.test_status_label.setAlignment(Qt.AlignCenter)
        self.test_status_label.setStyleSheet("""
            QLabel {
                padding: 8px;
                border-radius: 6px;
                font-weight: 500;
                font-size: 13px;
            }
        """)
        
        # Button Box
        button_box = QDialogButtonBox(QDialogButtonBox.Save | 
                                     QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.save_settings)
        button_box.rejected.connect(self.reject)
        
        # Style the button box
        button_box.setStyleSheet(f"""
            QDialogButtonBox QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                min-width: 80px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
            QDialogButtonBox QPushButton:pressed {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
            QDialogButtonBox QPushButton[text="Cancel"] {{
                background: {colors['text_muted']};
                color: white;
            }}
            QDialogButtonBox QPushButton[text="Cancel"]:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        
        # Add to layout
        layout.addWidget(tts_group)
        layout.addWidget(url_group)
        layout.addWidget(general_group)
        layout.addWidget(test_button)
        layout.addWidget(self.test_status_label)
        layout.addStretch()
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

# Status change dialog class
class StatusChangeDialog(QDialog):
    def __init__(self, current_group=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Change Status")
        self.setModal(True)
        self.setFixedSize(400, 300)
        
        # Store the current group
        self.current_group = current_group
        
        # Center the dialog on screen
        self.center_on_screen()
        
        # Setup UI
        self.setup_ui()
        
        # Store result data
        self.result_data = None
        
    def center_on_screen(self):
        """Center the dialog on the screen"""
        screen = QApplication.primaryScreen().geometry()
        dialog_geometry = self.geometry()
        x = (screen.width() - dialog_geometry.width()) // 2
        y = (screen.height() - dialog_geometry.height()) // 2
        self.move(x, y)
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Get adaptive colors for styling
        colors = get_adaptive_colors()
        
        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)
        
        # Title label
        title_label = QLabel(f"Change {self.current_group} Status")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"font-weight: bold; font-size: 16px; margin-bottom: 10px; color: {colors['text_primary']};")
        layout.addWidget(title_label)
        
        # Form layout for controls
        form_layout = QFormLayout()
        form_layout.setSpacing(12)
        
        # Style form labels
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Actions dropdown
        self.action_combo = QComboBox()
        self.action_combo.addItem("Normal", "normal")
        self.action_combo.addItem("Warning", "warning") 
        self.action_combo.addItem("Acknowledged", "alert-acked")
        self.action_combo.addItem("Alert", "alert")
        self.action_combo.setStyleSheet(f"""
            QComboBox {{
                background: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                color: {colors['text_primary']};
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {colors['text_secondary']};
                margin-right: 5px;
            }}
            QComboBox QAbstractItemView {{
                background: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                selection-background-color: {colors['accent_blue']};
                selection-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)
        
        action_label = QLabel("Action:")
        action_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 500;")
        form_layout.addRow(action_label, self.action_combo)
        
        # Reason text box
        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Enter reason for status change...")
        self.reason_input.setStyleSheet(f"""
            QLineEdit {{
                background: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 14px;
                color: {colors['text_primary']};
            }}
            QLineEdit:hover {{
                border-color: {colors['accent_blue']};
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
                outline: none;
            }}
        """)
        
        reason_label = QLabel("Reason:")
        reason_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 500;")
        form_layout.addRow(reason_label, self.reason_input)
        
        # Group display (read-only, showing the clicked group)
        self.group_label = QLabel(self.current_group if self.current_group else "Unknown")
        self.group_label.setStyleSheet(f"font-weight: bold; color: {colors['accent_blue']}; padding: 8px 12px; border: 1px solid {colors['border_secondary']}; border-radius: 6px; background-color: {colors['bg_secondary']};")
        
        group_label = QLabel("Group:")
        group_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: 500;")
        form_layout.addRow(group_label, self.group_label)
        
        layout.addLayout(form_layout)
        
        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        submit_button = button_box.button(QDialogButtonBox.Ok)
        submit_button.setText("Submit")
        cancel_button = button_box.button(QDialogButtonBox.Cancel)
        cancel_button.setText("Cancel")
        
        # Style the button box
        button_box.setStyleSheet(f"""
            QDialogButtonBox QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
                min-width: 80px;
            }}
            QDialogButtonBox QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
            QDialogButtonBox QPushButton:pressed {{
                background: {colors['bg_tertiary']};
                color: {colors['text_primary']};
            }}
            QDialogButtonBox QPushButton[text="Cancel"] {{
                background: {colors['text_muted']};
                color: white;
            }}
            QDialogButtonBox QPushButton[text="Cancel"]:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        
        button_box.accepted.connect(self.accept_change)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        # Set focus to reason input
        self.reason_input.setFocus()
        
    def accept_change(self):
        """Validate and accept the status change"""
        action = self.action_combo.currentData()
        reason = self.reason_input.text().strip()
        group = self.current_group  # Use the current group instead of dropdown
        
        # Basic validation
        if not reason:
            QMessageBox.warning(self, "Validation Error", "Please enter a reason for the status change.")
            self.reason_input.setFocus()
            return
        
        # Store the result data
        self.result_data = {
            'action': action,
            'reason': reason,
            'group': group
        }
        
        # Call API to submit the status change
        self.submit_to_api(self.result_data)
        
        # Accept the dialog
        self.accept()
    
    def submit_to_api(self, data):
        """Submit the status change to the API"""
        try:
            # Get parent window to access credentials
            parent_app = self.parent()
            if not parent_app or not hasattr(parent_app, 'username') or not hasattr(parent_app, 'password'):
                QMessageBox.warning(self, "API Error", "No authentication credentials available.")
                return
            
            # Prepare API request
            api_url = "https://busylight.signalwire.me/api/status"
            
            payload = {
                'group': data['group'],
                'status': data['action'],
                'reason': data['reason'],
                'timestamp': get_timestamp(),
                'source': parent_app.username
            }
            
            headers = {
                'Content-Type': 'application/json'
            }
            
            # Make API call with authentication
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                auth=(parent_app.username, parent_app.password),
                timeout=10
            )
            
            if response.status_code == 200:
                # Success
                if hasattr(parent_app, 'add_log'):
                    parent_app.add_log(f"[{get_timestamp()}] API: Status change submitted successfully for group '{data['group']}'")
            else:
                # API error
                error_msg = f"API Error: HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    if 'error' in error_data:
                        error_msg += f" - {error_data['error']}"
                except:
                    pass
                
                QMessageBox.warning(self, "API Error", f"Failed to submit status change:\n{error_msg}")
                if hasattr(parent_app, 'add_log'):
                    parent_app.add_log(f"[{get_timestamp()}] API Error: {error_msg}")
                    
        except requests.exceptions.Timeout:
            QMessageBox.warning(self, "API Error", "Request timed out. Please try again.")
            if hasattr(parent_app, 'add_log'):
                parent_app.add_log(f"[{get_timestamp()}] API Error: Request timed out")
                
        except requests.exceptions.ConnectionError:
            QMessageBox.warning(self, "API Error", "Could not connect to the API server.")
            if hasattr(parent_app, 'add_log'):
                parent_app.add_log(f"[{get_timestamp()}] API Error: Connection failed")
                
        except Exception as e:
            QMessageBox.warning(self, "API Error", f"Unexpected error: {str(e)}")
            if hasattr(parent_app, 'add_log'):
                parent_app.add_log(f"[{get_timestamp()}] API Error: {str(e)}")
    
    def get_result(self):
        """Return the result data"""
        return self.result_data

# Analytics Dashboard class
class AnalyticsDashboard(QDialog):
    def __init__(self, redis_info, username, password, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ticket Analytics Dashboard")
        self.setModal(False)
        self.resize(1200, 800)
        
        # Store credentials and Redis info
        self.redis_info = redis_info
        self.username = username
        self.password = password
        
        # Initialize Redis connection
        self.redis_client = None
        self.pubsub = None
        
        # Data storage
        self.current_stats = None
        self.ticket_timeline = []  # Store historical ticket counts for timeline
        
        # Setup UI
        self.setup_ui()
        
        # Connect to Redis and start listening
        self.connect_redis()
        
        # Timer for periodic updates
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.refresh_data)
        self.update_timer.start(30000)  # Update every 30 seconds
        
        # Initial data load
        self.refresh_data()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Get adaptive colors
        colors = get_adaptive_colors()
        
        # Set dialog styling
        self.setStyleSheet(f"""
            QDialog {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QGroupBox {{
                border: 2px solid {colors['border_secondary']};
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                font-weight: 600;
                font-size: 14px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        
        # Header
        header_label = QLabel("Ticket Analytics Dashboard")
        header_label.setAlignment(Qt.AlignCenter)
        header_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {colors['text_primary']};
            margin-bottom: 20px;
        """)
        layout.addWidget(header_label)
        
        # Last updated label
        self.last_updated_label = QLabel("Last Updated: Never")
        self.last_updated_label.setAlignment(Qt.AlignCenter)
        self.last_updated_label.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic; margin-bottom: 10px;")
        layout.addWidget(self.last_updated_label)
        
        # Create scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {colors['bg_secondary']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {colors['text_muted']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {colors['accent_blue']};
            }}
        """)
        
        # Main content widget
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(20)
        
        # Top metrics row - Total tickets
        total_layout = QHBoxLayout()
        
        # Total tickets metric
        self.total_tickets_group = QGroupBox("Total Open Tickets")
        total_group_layout = QVBoxLayout(self.total_tickets_group)
        self.total_tickets_label = QLabel("0")
        self.total_tickets_label.setAlignment(Qt.AlignCenter)
        self.total_tickets_label.setStyleSheet(f"""
            font-size: 48px;
            font-weight: bold;
            color: {colors['accent_blue']};
            background: transparent;
        """)
        total_group_layout.addWidget(self.total_tickets_label)
        total_layout.addWidget(self.total_tickets_group)
        
        # Categories with tickets metric
        self.categories_count_group = QGroupBox("Active Categories")
        categories_count_layout = QVBoxLayout(self.categories_count_group)
        self.categories_count_label = QLabel("0")
        self.categories_count_label.setAlignment(Qt.AlignCenter)
        self.categories_count_label.setStyleSheet(f"""
            font-size: 36px;
            font-weight: bold;
            color: {colors['accent_green']};
            background: transparent;
        """)
        categories_count_layout.addWidget(self.categories_count_label)
        total_layout.addWidget(self.categories_count_group)
        
        # Languages metric
        self.languages_count_group = QGroupBox("Languages")
        languages_count_layout = QVBoxLayout(self.languages_count_group)
        self.languages_count_label = QLabel("0")
        self.languages_count_label.setAlignment(Qt.AlignCenter)
        self.languages_count_label.setStyleSheet(f"""
            font-size: 36px;
            font-weight: bold;
            color: {colors['accent_orange']};
            background: transparent;
        """)
        languages_count_layout.addWidget(self.languages_count_label)
        total_layout.addWidget(self.languages_count_group)
        
        content_layout.addLayout(total_layout)
        
        # Charts row - Priority and Category pie charts
        charts_layout = QHBoxLayout()
        
        # Priority pie chart
        self.priority_group = QGroupBox("Priority Breakdown")
        priority_layout = QVBoxLayout(self.priority_group)
        self.priority_chart = PieChartWidget()
        self.priority_chart.setMinimumSize(300, 250)
        priority_layout.addWidget(self.priority_chart)
        charts_layout.addWidget(self.priority_group)
        
        # Category bar chart
        self.category_group = QGroupBox("Category Breakdown")
        category_layout = QVBoxLayout(self.category_group)
        self.category_chart = BarChartWidget()
        self.category_chart.setMinimumSize(300, 250)
        category_layout.addWidget(self.category_chart)
        charts_layout.addWidget(self.category_group)
        
        content_layout.addLayout(charts_layout)
        
        # Timeline chart for ticket counts over time
        self.timeline_group = QGroupBox("Ticket Count Timeline")
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline_chart = TimelineChartWidget()
        self.timeline_chart.setMinimumHeight(200)
        timeline_layout.addWidget(self.timeline_chart)
        content_layout.addWidget(self.timeline_group)
        
        # Recent tickets table
        self.recent_tickets_group = QGroupBox("Recent Tickets")
        recent_layout = QVBoxLayout(self.recent_tickets_group)
        self.recent_tickets_text = QTextEdit()
        self.recent_tickets_text.setReadOnly(True)
        self.recent_tickets_text.setMinimumHeight(300)
        self.recent_tickets_text.setStyleSheet(f"""
            background: {colors['input_bg']};
            border: 1px solid {colors['input_border']};
            border-radius: 8px;
            padding: 12px;
            color: {colors['text_secondary']};
            font-family: 'Monaco', 'Consolas', monospace;
            font-size: 11px;
            line-height: 1.4;
        """)
        recent_layout.addWidget(self.recent_tickets_text)
        content_layout.addWidget(self.recent_tickets_group)
        
        # Control buttons
        button_layout = QHBoxLayout()
        
        self.refresh_button = QPushButton("Refresh Data")
        self.refresh_button.clicked.connect(self.refresh_data)
        self.refresh_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        self.close_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['text_muted']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        
        button_layout.addWidget(self.refresh_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_button)
        content_layout.addLayout(button_layout)
        
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)
        
    def connect_redis(self):
        """Connect to Redis using the provided credentials"""
        try:
            if self.redis_info:
                self.redis_client = redis.StrictRedis(
                    host=self.redis_info['host'],
                    port=self.redis_info['port'],
                    password=self.redis_info['password'],
                    db=0,
                    decode_responses=True,
                    socket_timeout=10,
                    socket_connect_timeout=10
                )
                self.redis_client.ping()
                print(f"[{get_timestamp()}] Analytics dashboard connected to Redis")
                
                # Subscribe to ticket stats updates
                self.pubsub = self.redis_client.pubsub()
                self.pubsub.subscribe("ticket_stats_channel")
                
                # Start listening thread
                self.listen_thread = QThread()
                self.listener = TicketStatsListener(self.pubsub)
                self.listener.moveToThread(self.listen_thread)
                self.listener.stats_updated.connect(self.handle_stats_update)
                self.listen_thread.started.connect(self.listener.run)
                self.listen_thread.start()
                
        except Exception as e:
            print(f"[{get_timestamp()}] Analytics dashboard Redis connection error: {e}")
    
    def refresh_data(self):
        """Refresh data from Redis"""
        try:
            if not self.redis_client:
                return
                
            # Load historical data from ticket_stats queue if timeline is empty
            if not self.ticket_timeline:
                self.load_historical_timeline_data()
                
            # Get latest ticket stats
            latest_stats = self.redis_client.get("latest_ticket_stats")
            if latest_stats:
                stats_data = json.loads(latest_stats)
                self.update_dashboard(stats_data)
            else:
                # Try to get from the list
                stats_list = self.redis_client.lrange("ticket_stats", 0, 0)
                if stats_list:
                    stats_data = json.loads(stats_list[0])
                    self.update_dashboard(stats_data)
                    
        except Exception as e:
            print(f"[{get_timestamp()}] Error refreshing analytics data: {e}")
    
    def load_historical_timeline_data(self):
        """Load the previous 20 events from ticket_stats to populate timeline"""
        try:
            # Get the last 20 events from the ticket_stats list (most recent first)
            historical_stats = self.redis_client.lrange("ticket_stats", 0, 19)
            
            if historical_stats:
                print(f"[{get_timestamp()}] Loading {len(historical_stats)} historical ticket stats for timeline")
                
                # Process events in reverse order (oldest first) to build timeline correctly
                for stats_json in reversed(historical_stats):
                    try:
                        stats_data = json.loads(stats_json)
                        data = stats_data.get('data', {})
                        total_tickets = data.get('total_tickets', 0)
                        
                        # Parse the timestamp from the event
                        created_at_str = stats_data.get('created_at', '')
                        if created_at_str:
                            # Parse ISO format timestamp
                            import datetime
                            try:
                                timestamp = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                                # Convert to local time if needed
                                timestamp = timestamp.replace(tzinfo=None)
                            except:
                                # Fallback to current time if parsing fails
                                timestamp = datetime.datetime.now()
                        else:
                            timestamp = datetime.datetime.now()
                        
                        # Add to timeline
                        self.ticket_timeline.append({
                            'timestamp': timestamp,
                            'count': total_tickets
                        })
                        
                    except json.JSONDecodeError as e:
                        print(f"[{get_timestamp()}] Error parsing historical stats: {e}")
                        continue
                
                # Keep only last 100 data points for performance
                if len(self.ticket_timeline) > 100:
                    self.ticket_timeline = self.ticket_timeline[-100:]
                
                print(f"[{get_timestamp()}] Loaded {len(self.ticket_timeline)} historical data points for timeline")
                
                # Update the timeline chart with historical data
                self.timeline_chart.set_data(self.ticket_timeline)
                
        except Exception as e:
            print(f"[{get_timestamp()}] Error loading historical timeline data: {e}")
    
    def handle_stats_update(self, stats_data):
        """Handle real-time stats updates"""
        try:
            self.update_dashboard(stats_data)
        except Exception as e:
            print(f"[{get_timestamp()}] Error handling stats update: {e}")
    
    def update_dashboard(self, stats_data):
        """Update the dashboard with new stats data"""
        try:
            self.current_stats = stats_data
            data = stats_data.get('data', {})
            
            # Update last updated time
            created_at = stats_data.get('created_at', 'Unknown')
            self.last_updated_label.setText(f"Last Updated: {created_at}")
            
            # Update total tickets
            total_tickets = data.get('total_tickets', 0)
            self.total_tickets_label.setText(str(total_tickets))
            
            # Update categories count (number of categories with tickets)
            categories = data.get('categories', {})
            active_categories = len([cat for cat, count in categories.items() if count > 0])
            self.categories_count_label.setText(str(active_categories))
            
            # Update languages count
            languages = data.get('languages', {})
            language_count = len([lang for lang, count in languages.items() if count > 0])
            self.languages_count_label.setText(str(language_count))
            
            # Add to timeline data
            import datetime
            timestamp = datetime.datetime.now()
            
            # Only add new timeline data if this represents a real change
            # Check if this is significantly different from the last data point
            should_add_point = True
            if self.ticket_timeline:
                last_point = self.ticket_timeline[-1]
                time_diff = (timestamp - last_point['timestamp']).total_seconds()
                count_diff = abs(total_tickets - last_point['count'])
                
                # Only add if enough time has passed (30+ seconds) OR ticket count changed
                if time_diff < 30 and count_diff == 0:
                    should_add_point = False
            
            if should_add_point:
                self.ticket_timeline.append({
                    'timestamp': timestamp,
                    'count': total_tickets
                })
                
                # Keep only last 100 data points for performance
                if len(self.ticket_timeline) > 100:
                    self.ticket_timeline = self.ticket_timeline[-100:]
                
                # Update timeline chart
                self.timeline_chart.set_data(self.ticket_timeline)
            
            # Update priority pie chart
            priorities = data.get('priorities', {})
            self.priority_chart.set_data(priorities, "Priority Distribution")
            
            # Update category bar chart
            self.category_chart.set_data(categories, "Category Distribution")
            
            # Update recent tickets
            self.update_recent_tickets(data.get('tickets', []))
            
        except Exception as e:
            print(f"[{get_timestamp()}] Error updating dashboard: {e}")
    
    def update_recent_tickets(self, tickets):
        """Update the recent tickets display"""
        try:
            recent_text = ""
            for i, ticket in enumerate(tickets[:10]):  # Show only first 10
                ticket_num = ticket.get('ticket_number', 'Unknown')
                classification = ticket.get('classification', {})
                category = classification.get('category', 'Unknown')
                priority = classification.get('priority', 'Unknown')
                summary = classification.get('summary', 'No summary available')
                
                # Truncate summary if too long
                if len(summary) > 80:
                    summary = summary[:77] + "..."
                
                recent_text += f"#{ticket_num} [{category}] [{priority}]\n"
                recent_text += f"  {summary}\n\n"
                
            self.recent_tickets_text.setPlainText(recent_text.strip())
            
        except Exception as e:
            print(f"[{get_timestamp()}] Error updating recent tickets: {e}")
    
    def closeEvent(self, event):
        """Clean up when closing"""
        try:
            if hasattr(self, 'listen_thread') and self.listen_thread:
                if hasattr(self, 'listener'):
                    self.listener.stop()
                self.listen_thread.quit()
                self.listen_thread.wait(1000)
            if self.pubsub:
                self.pubsub.close()
        except:
            pass
        event.accept()

# Custom Pie Chart Widget
class PieChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.title = "Chart"
        self.colors = [
            '#4285f4',  # Google Blue
            '#34a853',  # Google Green  
            '#fbbc05',  # Google Yellow
            '#ea4335',  # Google Red
            '#9c27b0',  # Material Purple
            '#ff9800',  # Material Orange
            '#00bcd4',  # Material Cyan
            '#795548',  # Material Brown
            '#e91e63',  # Material Pink
            '#009688',  # Material Teal
            '#607d8b',  # Material Blue Grey
            '#3f51b5',  # Material Indigo
        ]
        
    def set_data(self, data, title="Chart"):
        """Set the data for the pie chart"""
        self.data = data
        self.title = title
        self.update()  # Trigger a repaint
    
    def paintEvent(self, event):
        """Custom paint event to draw the pie chart"""
        if not self.data:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get adaptive colors
        colors = get_adaptive_colors()
        
        # Calculate total for percentages
        total = sum(self.data.values())
        if total == 0:
            return
        
        # Chart area - improved sizing
        margin = 30
        legend_width = 180
        chart_size = min(self.width() - margin * 2 - legend_width, self.height() - margin * 2 - 40)
        chart_rect = QRect(margin, margin + 40, chart_size, chart_size)
        
        # Draw title with better styling
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, self.title)
        
        # Draw shadow for depth
        shadow_offset = 3
        shadow_rect = chart_rect.adjusted(shadow_offset, shadow_offset, shadow_offset, shadow_offset)
        painter.setBrush(QColor(0, 0, 0, 30))  # Semi-transparent black
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(shadow_rect)
        
        # Draw pie slices with improved styling
        start_angle = 0
        legend_y = chart_rect.top()
        
        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)
        
        for i, (label, value) in enumerate(sorted_data):
            # Calculate slice angle
            span_angle = int((value / total) * 360 * 16)  # 16ths of degrees for Qt
            
            # Set color with gradient effect
            base_color = QColor(self.colors[i % len(self.colors)])
            painter.setBrush(base_color)
            painter.setPen(QColor(colors['bg_primary']))  # Thin white border
            
            # Draw slice
            painter.drawPie(chart_rect, start_angle, span_angle)
            
            # Draw legend with better spacing and alignment
            legend_x = chart_rect.right() + 20
            legend_color_rect = QRect(legend_x, legend_y + 2, 16, 16)
            
            # Legend color box with border
            painter.setBrush(base_color)
            painter.setPen(QColor(colors['border_secondary']))
            painter.drawRect(legend_color_rect)
            
            # Legend text with better formatting
            painter.setPen(QColor(colors['text_primary']))
            text_font = QFont()
            text_font.setPointSize(10)
            painter.setFont(text_font)
            
            percentage = (value / total) * 100
            # Truncate long labels
            display_label = label if len(label) <= 12 else label[:9] + "..."
            legend_text = f"{display_label}: {value} ({percentage:.1f}%)"
            text_rect = QRect(legend_x + 22, legend_y, legend_width - 22, 20)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, legend_text)
            
            start_angle += span_angle
            legend_y += 25  # Better spacing between legend items

# Custom Bar Chart Widget
class BarChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = {}
        self.title = "Chart"
        self.colors = [
            '#4285f4',  # Google Blue
            '#34a853',  # Google Green  
            '#fbbc05',  # Google Yellow
            '#ea4335',  # Google Red
            '#9c27b0',  # Material Purple
            '#ff9800',  # Material Orange
            '#00bcd4',  # Material Cyan
            '#795548',  # Material Brown
            '#e91e63',  # Material Pink
            '#009688',  # Material Teal
            '#607d8b',  # Material Blue Grey
            '#3f51b5',  # Material Indigo
        ]
        
    def set_data(self, data, title="Chart"):
        """Set the data for the bar chart"""
        self.data = data
        self.title = title
        self.update()  # Trigger a repaint
    
    def paintEvent(self, event):
        """Custom paint event to draw the bar chart"""
        if not self.data:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get adaptive colors
        colors = get_adaptive_colors()
        
        # Calculate total for percentages
        total = sum(self.data.values())
        if total == 0:
            return
        
        # Chart area
        margin = 30
        chart_rect = self.rect().adjusted(margin, margin + 40, -margin, -margin - 30)
        
        # Draw title
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, self.title)
        
        # Sort data by value (descending)
        sorted_data = sorted(self.data.items(), key=lambda x: x[1], reverse=True)
        
        if not sorted_data:
            return
            
        # Calculate bar dimensions
        num_bars = len(sorted_data)
        bar_width = chart_rect.width() / num_bars * 0.8  # 80% width, 20% spacing
        bar_spacing = chart_rect.width() / num_bars * 0.2
        max_value = max(item[1] for item in sorted_data)
        
        if max_value == 0:
            max_value = 1  # Avoid division by zero
        
        # Draw axes
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight())  # X-axis
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())      # Y-axis
        
        # Draw grid lines for better readability
        painter.setPen(QColor(colors['border_secondary']))
        for i in range(1, 5):  # 4 horizontal grid lines
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            painter.drawLine(chart_rect.left(), int(y_pos), chart_rect.right(), int(y_pos))
        
        # Draw bars
        for i, (label, value) in enumerate(sorted_data):
            # Calculate bar position and height
            bar_height = (value / max_value) * chart_rect.height()
            bar_x = chart_rect.left() + i * (bar_width + bar_spacing) + bar_spacing / 2
            bar_y = chart_rect.bottom() - bar_height
            
            # Create bar rectangle
            bar_rect = QRect(int(bar_x), int(bar_y), int(bar_width), int(bar_height))
            
            # Set color
            color = QColor(self.colors[i % len(self.colors)])
            painter.setBrush(color)
            painter.setPen(QColor(colors['bg_primary']))
            
            # Draw bar with shadow effect
            shadow_rect = bar_rect.adjusted(2, 2, 2, 2)
            painter.setBrush(QColor(0, 0, 0, 30))
            painter.setPen(Qt.NoPen)
            painter.drawRect(shadow_rect)
            
            # Draw main bar
            painter.setBrush(color)
            painter.setPen(QColor(colors['bg_primary']))
            painter.drawRect(bar_rect)
            
            # Draw value on top of bar
            painter.setPen(QColor(colors['text_primary']))
            value_font = QFont()
            value_font.setPointSize(9)
            value_font.setBold(True)
            painter.setFont(value_font)
            
            value_rect = QRect(int(bar_x), int(bar_y) - 20, int(bar_width), 15)
            painter.drawText(value_rect, Qt.AlignCenter, str(value))
            
            # Draw label below bar (rotated for better fit)
            painter.save()
            label_font = QFont()
            label_font.setPointSize(8)
            painter.setFont(label_font)
            
            # Truncate long labels
            display_label = label if len(label) <= 8 else label[:5] + "..."
            
            # Position for rotated text
            label_x = bar_x + bar_width / 2
            label_y = chart_rect.bottom() + 15
            
            painter.translate(label_x, label_y)
            painter.rotate(-45)  # Rotate text 45 degrees
            painter.drawText(-30, 0, 60, 15, Qt.AlignCenter, display_label)
            painter.restore()
        
        # Draw Y-axis labels
        painter.setPen(QColor(colors['text_secondary']))
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        
        for i in range(5):  # 5 Y-axis labels
            y_val = (max_value / 4) * i
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            
            label_rect = QRect(5, int(y_pos) - 10, margin - 10, 20)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{int(y_val)}")

# Custom Timeline Chart Widget  
class TimelineChartWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data = []
        self.hover_point = None  # Track which point is being hovered
        self.data_points = []    # Store rendered point positions for hit testing
        self.setMouseTracking(True)  # Enable mouse tracking for tooltips
        
    def set_data(self, timeline_data):
        """Set the timeline data"""
        self.timeline_data = timeline_data
        self.update()  # Trigger repaint
        
    def mouseMoveEvent(self, event):
        """Handle mouse movement for tooltips"""
        mouse_pos = event.pos()
        self.hover_point = None
        
        # Check if mouse is over any data point
        for i, (point, data) in enumerate(self.data_points):
            distance = ((mouse_pos.x() - point.x()) ** 2 + (mouse_pos.y() - point.y()) ** 2) ** 0.5
            if distance <= 8:  # Within 8 pixels of the point
                self.hover_point = i
                self.setToolTip(f"Time: {data['timestamp'].strftime('%H:%M:%S')}\nTickets: {data['count']}")
                break
        
        if self.hover_point is None:
            self.setToolTip("")  # Clear tooltip
            
        self.update()  # Redraw to highlight hovered point
        
    def paintEvent(self, event):
        """Custom paint event to draw the timeline chart"""
        if not self.timeline_data or len(self.timeline_data) < 1:
            return
            
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get adaptive colors
        colors = get_adaptive_colors()
        
        # Chart area with better margins
        margin = 50
        chart_rect = self.rect().adjusted(margin, margin + 30, -margin, -margin - 20)
        
        # Draw title with improved styling
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, "Ticket Count Over Time")
        
        # Handle single data point case
        if len(self.timeline_data) == 1:
            # Draw single point in center
            center_x = chart_rect.center().x()
            center_y = chart_rect.center().y()
            point = QPoint(center_x, center_y)
            
            painter.setBrush(QColor(colors['accent_blue']))
            painter.setPen(QColor(colors['accent_blue']))
            painter.drawEllipse(point, 6, 6)
            
            # Store for tooltip
            self.data_points = [(point, self.timeline_data[0])]
            
            # Draw count label
            painter.setPen(QColor(colors['text_primary']))
            label_font = QFont()
            label_font.setPointSize(12)
            painter.setFont(label_font)
            painter.drawText(center_x - 20, center_y - 20, 40, 15, Qt.AlignCenter, str(self.timeline_data[0]['count']))
            return
        
        # Find min/max values for scaling
        counts = [point['count'] for point in self.timeline_data]
        min_count = min(counts)
        max_count = max(counts)
        
        if max_count == min_count:
            max_count = min_count + 1  # Avoid division by zero
        
        # Draw grid lines for better readability
        painter.setPen(QColor(colors['border_secondary']))
        for i in range(5):  # 5 horizontal grid lines
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            painter.drawLine(chart_rect.left(), int(y_pos), chart_rect.right(), int(y_pos))
        
        # Draw axes with improved styling
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight())  # X-axis
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())      # Y-axis
        
        # Calculate and store data points
        points = []
        self.data_points = []
        
        for i, data_point in enumerate(self.timeline_data):
            count = data_point['count']
            
            # Calculate position
            x = chart_rect.left() + (i / (len(self.timeline_data) - 1)) * chart_rect.width()
            y = chart_rect.bottom() - ((count - min_count) / (max_count - min_count)) * chart_rect.height()
            
            point = QPoint(int(x), int(y))
            points.append(point)
            self.data_points.append((point, data_point))
        
        # Draw line connecting points with gradient effect
        painter.setPen(QColor(colors['accent_blue']))
        painter.setPen(QPen(QColor(colors['accent_blue']), 2))  # Thicker line
        for i in range(len(points) - 1):
            painter.drawLine(points[i], points[i + 1])
        
        # Draw data points with improved styling
        for i, (point, data) in enumerate(self.data_points):
            if i == self.hover_point:
                # Highlight hovered point
                painter.setBrush(QColor(colors['accent_orange']))
                painter.setPen(QColor(colors['accent_orange']))
                painter.drawEllipse(point, 8, 8)  # Larger when hovered
                
                # Draw count label for hovered point
                painter.setPen(QColor(colors['text_primary']))
                label_font = QFont()
                label_font.setPointSize(10)
                label_font.setBold(True)
                painter.setFont(label_font)
                label_rect = QRect(point.x() - 15, point.y() - 25, 30, 15)
                painter.drawText(label_rect, Qt.AlignCenter, str(data['count']))
            else:
                # Normal point
                painter.setBrush(QColor(colors['accent_blue']))
                painter.setPen(QColor(colors['bg_primary']))
                painter.drawEllipse(point, 5, 5)
        
        # Draw Y-axis labels with better formatting
        painter.setPen(QColor(colors['text_secondary']))
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)
        
        # Y-axis labels (ticket counts)
        for i in range(5):  # 5 labels
            y_val = min_count + (max_count - min_count) * (i / 4)
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            
            label_rect = QRect(5, int(y_pos) - 10, margin - 10, 20)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{int(y_val)}")
        
        # Draw X-axis time labels with better spacing
        if len(self.timeline_data) > 1:
            # Show multiple time points if we have enough data
            num_labels = min(5, len(self.timeline_data))
            for i in range(num_labels):
                data_index = int(i * (len(self.timeline_data) - 1) / (num_labels - 1))
                time_str = self.timeline_data[data_index]['timestamp'].strftime("%H:%M")
                x_pos = chart_rect.left() + (data_index / (len(self.timeline_data) - 1)) * chart_rect.width()
                
                time_rect = QRect(int(x_pos) - 20, chart_rect.bottom() + 5, 40, 20)
                painter.drawText(time_rect, Qt.AlignCenter, time_str)

# Ticket stats listener for real-time updates
class TicketStatsListener(QObject):
    stats_updated = pyqtSignal(dict)
    
    def __init__(self, pubsub):
        super().__init__()
        self.pubsub = pubsub
        self.is_running = True
    
    def run(self):
        """Listen for ticket stats updates"""
        while self.is_running:
            try:
                message = self.pubsub.get_message(timeout=0.1)
                if message and message["type"] == "message":
                    stats_data = json.loads(message["data"])
                    self.stats_updated.emit(stats_data)
            except Exception as e:
                print(f"[{get_timestamp()}] Error in ticket stats listener: {e}")
            
            # Small sleep to prevent CPU hogging
            QThread.msleep(100)
    
    def stop(self):
        """Stop the listener"""
        self.is_running = False

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
            # Track both user's groups (for overall status) and all groups (for monitoring)
            self.user_groups = redis_info['groups']  # Groups user is a member of
            self.groups = redis_info.get('all_groups', redis_info['groups'])  # All groups to subscribe to
        else:
            # Fallback to default values if no redis_info provided
            self.redis_host = "localhost"
            self.redis_port = 6379
            self.redis_password = None
            self.user_groups = ["default"]
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
            
        # Get the most recent status from group-specific status keys
        try:
            latest_status = None
            group_found_status = {}
            
            # Get the most recent status for each group from their individual status keys
            for group in self.groups:
                status_key = f"status:{group}"
                try:
                    # Get the most recent status event for this group
                    recent_event = self.redis_client.lindex(status_key, 0)  # Most recent is at index 0
                    if recent_event:
                        try:
                            data = json.loads(recent_event)
                            event_status = data.get('status')
                            
                            if event_status:
                                group_found_status[group] = {
                                    'status': event_status,
                                    'data': data
                                }
                                self.log_message.emit(f"[{get_timestamp()}] Found recent status for group '{group}': {event_status}")

                                # Use first status found as overall status (only for user's groups)
                                if latest_status is None and group in self.user_groups:
                                    latest_status = event_status
                                    self.log_message.emit(f"[{get_timestamp()}] Setting initial overall status to '{latest_status}' from user group '{group}'")
                                    
                        except json.JSONDecodeError as e:
                            self.log_message.emit(f"[{get_timestamp()}] Error parsing status data for group '{group}': {e}")
                    else:
                        self.log_message.emit(f"[{get_timestamp()}] No status events found for group '{group}'")
                        
                except Exception as e:
                    self.log_message.emit(f"[{get_timestamp()}] Error accessing status key '{status_key}': {e}")
            
            # Emit status for each group (found status or default to normal)
            for group in self.groups:
                if group in group_found_status:
                    # Found a recent event for this group
                    status = group_found_status[group]['status']
                    data = group_found_status[group]['data']
                    self.group_status_updated.emit(group, status, data)
                    self.process_ticket_info(data, group)
                else:
                    # No recent event found, default to normal
                    self.log_message.emit(f"[{get_timestamp()}] No recent status found for group '{group}', defaulting to normal")
                    default_data = {'group': group, 'status': 'normal'}
                    self.group_status_updated.emit(group, 'normal', default_data)
            
            # Emit overall status
            if latest_status:
                self.status_updated.emit(latest_status)
            else:
                self.status_updated.emit('normal')
                
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Error getting initial status: {e}")
        
        # Subscribe to all group status channels
        pubsub = self.redis_client.pubsub()
        for group in self.groups:
            channel_name = f"status:{group}"
            pubsub.subscribe(channel_name)
            self.log_message.emit(f"[{get_timestamp()}] Subscribed to {channel_name}")
        
        self.log_message.emit(f"[{get_timestamp()}] Listening for messages on {len(self.groups)} status channels...")
        
        # Listen for messages in a loop
        while self.is_running:
            message = pubsub.get_message(timeout=0.1)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    channel = message["channel"]
                    # Extract group name from channel (remove 'status:' prefix)
                    group = channel.replace('status:', '') if channel.startswith('status:') else channel
                    
                    self.log_message.emit(f"[{get_timestamp()}] Received from {channel}: {data}")
                    status = data.get('status', 'error')
                    
                    # Emit group-specific status
                    self.group_status_updated.emit(group, status, data)

                    # Only emit overall status for groups the user is a member of (not monitoring groups)
                    if group in self.user_groups:
                        self.log_message.emit(f"[{get_timestamp()}] Updating overall status to '{status}' from user group '{group}'")
                        self.status_updated.emit(status)
                    else:
                        self.log_message.emit(f"[{get_timestamp()}] Group '{group}' status '{status}' - monitoring only, not affecting overall status")
                    
                    # Process ticket information if available
                    self.process_ticket_info(data, group)
                except Exception as e:
                    self.log_message.emit(f"[{get_timestamp()}] Error processing message: {e}")
                    self.status_updated.emit('error')
            
            # Small sleep to prevent CPU hogging
            QThread.msleep(100)
    
    def process_ticket_info(self, data, group):
        """Extract and process ticket information from a message"""
        # Check if this is a ticket message with required fields or has zoho_ticket_url
        if ('ticket' in data and 'status' in data) or 'zoho_ticket_url' in data:
            ticket_info = {
                'ticket': data.get('ticket', ''),
                'summary': data.get('summary', ''),
                'zoho_ticket_url': data.get('zoho_ticket_url', ''),
                'group': group
            }

            # Emit the ticket info for the main app to handle
            if ticket_info['ticket'] or ticket_info['zoho_ticket_url']:
                ticket_id = ticket_info['ticket'] if ticket_info['ticket'] else 'URL-only'
                self.log_message.emit(f"[{get_timestamp()}] Ticket information received: #{ticket_id}")
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
        'alert': "Red\n(Alert)",
        'alert-acked': "Orange\n(Alert-Acked)",
        'warning': "Yellow\n(Warning)",
        'error': "Purple\n(Error)",
        'normal': "Green\n(Normal)",
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
        self.username = username
        self.password = password
        self.redis_info = redis_info
        self.group_statuses = {}
        self.group_widgets = {}
        self.redis_worker = None
        self.worker_thread = None
        self.light_controller = None
        self.tray_icon = None
        self.tray_blink_timer = None
        self.is_tray_visible = True
        
        # Flag to prevent TTS during app initialization
        self.is_initializing = True
        
        # Setup window title and icon
        self.setWindowTitle("Busylight Controller")
        icon_path = get_resource_path("icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            # Fallback icon
            pixmap = QPixmap(64, 64)
            pixmap.fill(QColor(0, 255, 0))
            self.setWindowIcon(QIcon(pixmap))
        
        # Initialize blinking variables
        self.tray_blink_timer = QTimer(self)
        self.tray_blink_timer.timeout.connect(self.toggle_tray_icon)
        self.tray_icon_visible = True
        
        # Initialize the light controller first
        self.light_controller = LightController(self)
        
        # Create the main UI
        self.create_main_ui()
        
        # Set up system tray
        self.setup_tray()
        
        # Set up connections to UI after both UI and controller exist
        self.light_controller.log_message.connect(self.add_log)
        self.light_controller.color_changed.connect(self.update_status_display)
        self.light_controller.device_status_changed.connect(self.update_device_status)
        
        # Start the Redis worker after UI is ready
        self.start_redis_worker()
        
        # Explicitly refresh connection on startup after UI is ready
        QTimer.singleShot(100, self.manually_connect_device)
        
        # Mark initialization as complete after a short delay to allow startup events to process
        QTimer.singleShot(3000, self.complete_initialization)  # 3 second delay
    
    def create_main_ui(self):
        """Create the main UI components with tabbed interface"""
        main_widget = QWidget()
        layout = QVBoxLayout()

        # Get adaptive colors for styling
        colors = get_adaptive_colors()

        # Set the main window background color
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QWidget {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Set the main widget background
        main_widget.setStyleSheet(f"""
            QWidget {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Create main tab widget
        self.main_tab_widget = QTabWidget()
        self.main_tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
                background: transparent;
            }}
            QTabBar::tab {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                padding: 12px 20px;
                margin-right: 2px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                font-weight: 600;
                font-size: 14px;
            }}
            QTabBar::tab:selected {{
                background: {colors['accent_blue']};
                color: {colors['bg_primary']};
            }}
            QTabBar::tab:hover {{
                background: {colors['hover_bg']};
            }}
        """)

        # Create individual tabs
        self.create_status_monitor_tab(colors)
        self.create_analytics_tab(colors)
        self.create_configuration_tab(colors)

        layout.addWidget(self.main_tab_widget)
        main_widget.setLayout(layout)
        self.setCentralWidget(main_widget)

        # Set window size
        self.resize(900, 800)

    def create_status_monitor_tab(self, colors):
        """Create the Status Monitor tab"""
        status_tab = QWidget()
        layout = QVBoxLayout(status_tab)

        # Dynamic Group Status Section
        if self.redis_info and 'groups' in self.redis_info:
            groups_main = QGroupBox("Group Status Monitor")

            # Set bold font directly using Qt's font system
            bold_font = QFont()
            bold_font.setBold(True)
            bold_font.setPointSize(12)  # Larger size for prominence
            groups_main.setFont(bold_font)

            # Apply adaptive styling to the main Group Status Monitor
            groups_main.setStyleSheet(f"""
                QGroupBox {{
                    border: none;
                    border-radius: 12px;
                    margin: 8px;
                    padding: 16px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                    border: 2px solid {colors['border_secondary']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 16px;
                    padding: 0 8px 0 8px;
                    color: {colors['text_primary']};
                    font-weight: 800;
                    font-size: 16px;
                }}
            """)

            groups_main_layout = QVBoxLayout()

            # Create tab widget for My Groups / All Groups
            tab_widget = QTabWidget()
            tab_widget.setStyleSheet(f"""
                QTabWidget::pane {{
                    border: 1px solid {colors['border_secondary']};
                    border-radius: 8px;
                    background: transparent;
                }}
                QTabBar::tab {{
                    background: {colors['bg_secondary']};
                    color: {colors['text_primary']};
                    padding: 8px 16px;
                    margin-right: 2px;
                    border-top-left-radius: 8px;
                    border-top-right-radius: 8px;
                    font-weight: 600;
                }}
                QTabBar::tab:selected {{
                    background: {colors['accent_blue']};
                    color: {colors['bg_primary']};
                }}
                QTabBar::tab:hover {{
                    background: {colors['hover_bg']};
                }}
            """)

            # Tab 1: My Groups (full functionality)
            my_groups_tab = QWidget()
            my_groups_layout = QVBoxLayout(my_groups_tab)

            # Create a scrollable area for my groups
            my_scroll_area = QScrollArea()
            my_scroll_area.setWidgetResizable(True)
            my_scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    border: none;
                    background: transparent;
                }}
                QScrollBar:vertical {{
                    background: {colors['bg_secondary']};
                    width: 12px;
                    border-radius: 6px;
                }}
                QScrollBar::handle:vertical {{
                    background: {colors['text_muted']};
                    border-radius: 6px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {colors['accent_blue']};
                }}
            """)
            my_scroll_widget = QWidget()
            my_scroll_widget.setStyleSheet(f"background: transparent;")
            my_scroll_layout = QVBoxLayout(my_scroll_widget)

            # Create status widget for each group the user belongs to
            for group in self.redis_info['groups']:
                group_widget = self.create_full_group_widget(group, colors)
                my_scroll_layout.addWidget(group_widget)

            my_scroll_area.setWidget(my_scroll_widget)
            my_groups_layout.addWidget(my_scroll_area)

            # Tab 2: All Groups (display-only compact view)
            all_groups_tab = QWidget()
            all_groups_layout = QVBoxLayout(all_groups_tab)

            # Create a scrollable area for all groups
            all_scroll_area = QScrollArea()
            all_scroll_area.setWidgetResizable(True)
            all_scroll_area.setStyleSheet(f"""
                QScrollArea {{
                    border: none;
                    background: transparent;
                }}
                QScrollBar:vertical {{
                    background: {colors['bg_secondary']};
                    width: 12px;
                    border-radius: 6px;
                }}
                QScrollBar::handle:vertical {{
                    background: {colors['text_muted']};
                    border-radius: 6px;
                    min-height: 20px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background: {colors['accent_blue']};
                }}
            """)
            all_scroll_widget = QWidget()
            all_scroll_widget.setStyleSheet(f"background: transparent;")
            all_scroll_layout = QVBoxLayout(all_scroll_widget)

            # Create compact widgets for all groups (excluding user's groups)
            if 'all_groups' in self.redis_info:
                user_groups = set(self.redis_info['groups'])
                other_groups = [g for g in self.redis_info['all_groups'] if g not in user_groups]

                if other_groups:
                    # Create a grid layout for compact view
                    grid_layout = QGridLayout()
                    grid_layout.setSpacing(8)

                    row, col = 0, 0
                    max_cols = 4  # 4 compact widgets per row

                    for group in other_groups:
                        compact_widget = self.create_compact_group_widget(group, colors)
                        grid_layout.addWidget(compact_widget, row, col)

                        col += 1
                        if col >= max_cols:
                            col = 0
                            row += 1

                    # Create container widget for grid
                    grid_container = QWidget()
                    grid_container.setLayout(grid_layout)
                    all_scroll_layout.addWidget(grid_container)
                else:
                    # No other groups message
                    no_groups_label = QLabel("No other groups available")
                    no_groups_label.setAlignment(Qt.AlignCenter)
                    no_groups_label.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic; padding: 20px;")
                    all_scroll_layout.addWidget(no_groups_label)

            all_scroll_area.setWidget(all_scroll_widget)
            all_groups_layout.addWidget(all_scroll_area)

            # Add tabs to the tab widget
            tab_widget.addTab(my_groups_tab, "My Groups")
            tab_widget.addTab(all_groups_tab, "All Groups")

            groups_main_layout.addWidget(tab_widget)
            groups_main.setLayout(groups_main_layout)
            layout.addWidget(groups_main)
        else:
            # Fallback single status display if no groups
            status_group = QGroupBox("Status")

            # Set bold font directly using Qt's font system
            bold_font = QFont()
            bold_font.setBold(True)
            bold_font.setPointSize(12)
            status_group.setFont(bold_font)

            # Apply adaptive styling to the fallback status group
            status_group.setStyleSheet(f"""
                QGroupBox {{
                    border: none;
                    border-radius: 12px;
                    margin: 8px;
                    padding: 16px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                    border: 2px solid {colors['border_secondary']};
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 16px;
                    padding: 0 8px 0 8px;
                    color: {colors['text_primary']};
                    font-weight: 800;
                    font-size: 16px;
                }}
            """)

            status_layout = QVBoxLayout()

            self.status_label = QLabel("Status: Off")
            self.status_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {colors['text_primary']};")
            self.status_label.setAlignment(Qt.AlignCenter)
            status_layout.addWidget(self.status_label)

            status_group.setLayout(status_layout)
            layout.addWidget(status_group)

        self.main_tab_widget.addTab(status_tab, "Status Monitor")


    def create_configuration_tab(self, colors):
        """Create the Configuration tab with User Information and Settings"""
        config_tab = QWidget()
        config_layout = QVBoxLayout(config_tab)

        # Create scrollable area for configuration content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {colors['bg_secondary']};
                width: 12px;
                border-radius: 6px;
            }}
            QScrollBar::handle:vertical {{
                background: {colors['text_muted']};
                border-radius: 6px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        scroll_widget = QWidget()
        scroll_widget.setStyleSheet(f"background: transparent;")
        scroll_layout = QVBoxLayout(scroll_widget)

        # Add user information section at the top
        self.create_user_info_section(scroll_layout, colors)

        # Add configuration content
        self.create_config_content(scroll_layout, colors)

        scroll_area.setWidget(scroll_widget)
        config_layout.addWidget(scroll_area)

        # Add apply button at the bottom
        apply_button = QPushButton("Apply Settings")
        apply_button.clicked.connect(lambda: self.apply_config_settings())
        apply_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
                margin: 8px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        config_layout.addWidget(apply_button)

        self.main_tab_widget.addTab(config_tab, "Configuration")

    def create_user_info_section(self, layout, colors):
        """Create the user information section"""
        # User info section
        user_group = QGroupBox("User Information")

        # Set bold font
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(12)
        user_group.setFont(bold_font)

        user_group.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)

        user_layout = QHBoxLayout()

        if self.username:
            self.user_label = QLabel(f"Logged in as: {self.username}")
            self.user_label.setStyleSheet(f"color: {colors['accent_blue']}; font-weight: 500; font-size: 14px;")
            user_layout.addWidget(self.user_label)

        # Add some spacing
        user_layout.addStretch()

        # Device info with colored dot
        device_container = QWidget()
        device_layout = QHBoxLayout(device_container)
        device_layout.setContentsMargins(0, 0, 0, 0)
        device_layout.setSpacing(8)

        self.device_label = QLabel("Busylight: Disconnected")
        self.device_label.setStyleSheet(f"color: {colors['accent_red']}; font-weight: 500; font-size: 13px;")
        device_layout.addWidget(self.device_label)

        # Connection status dot
        self.connection_dot = QLabel("●")
        self.connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_red']}; font-weight: bold;")
        self.connection_dot.setToolTip("Busylight: Disconnected")
        device_layout.addWidget(self.connection_dot)

        user_layout.addWidget(device_container)

        # Add spacing between device and Redis
        user_layout.addSpacing(20)

        # Redis connection info with colored dot
        redis_container = QWidget()
        redis_layout = QHBoxLayout(redis_container)
        redis_layout.setContentsMargins(0, 0, 0, 0)
        redis_layout.setSpacing(8)

        self.redis_connection_label = QLabel("Disconnected")
        self.redis_connection_label.setStyleSheet(f"color: {colors['accent_red']}; font-weight: 500; font-size: 13px;")
        redis_layout.addWidget(self.redis_connection_label)

        # Redis connection status dot
        self.redis_connection_dot = QLabel("●")
        self.redis_connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_red']}; font-weight: bold;")
        self.redis_connection_dot.setToolTip("Disconnected")
        redis_layout.addWidget(self.redis_connection_dot)

        user_layout.addWidget(redis_container)

        user_group.setLayout(user_layout)
        layout.addWidget(user_group)

    def create_config_content(self, layout, colors):
        """Create the configuration content widgets"""
        # Load settings
        settings = QSettings("Busylight", "BusylightController")

        # Common QGroupBox styling
        group_style = f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """

        # Common checkbox styling
        checkbox_style = f"""
            QCheckBox {{
                font-size: 14px;
                color: {colors['text_primary']};
                font-weight: 500;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 4px;
                border: 2px solid {colors['border_secondary']};
                background: {colors['bg_primary']};
            }}
            QCheckBox::indicator:hover {{
                border-color: {colors['accent_blue']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['accent_blue']};
                border-color: {colors['accent_blue']};
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTIiIGhlaWdodD0iOSIgdmlld0JveD0iMCAwIDEyIDkiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxwYXRoIGQ9Ik0xIDQuNUw0LjUgOEwxMSAxIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIvPgo8L3N2Zz4K);
            }}
        """

        # TTS Configuration Group
        tts_group = QGroupBox("Text-to-Speech Configuration")

        # Set bold font
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(12)
        tts_group.setFont(bold_font)

        tts_group.setStyleSheet(group_style)
        tts_layout = QFormLayout(tts_group)
        tts_layout.setSpacing(12)

        self.tts_enabled_checkbox = QCheckBox()
        self.tts_enabled_checkbox.setStyleSheet(checkbox_style)
        self.tts_enabled_checkbox.setChecked(settings.value("tts/enabled", False, type=bool))
        tts_layout.addRow("Enable TTS:", self.tts_enabled_checkbox)

        layout.addWidget(tts_group)

        # URL Configuration Group
        url_group = QGroupBox("URL Handler Configuration")
        url_group.setFont(bold_font)
        url_group.setStyleSheet(group_style)
        url_layout = QFormLayout(url_group)
        url_layout.setSpacing(12)

        self.url_enabled_checkbox = QCheckBox()
        self.url_enabled_checkbox.setStyleSheet(checkbox_style)
        self.url_enabled_checkbox.setChecked(settings.value("url/enabled", False, type=bool))
        url_layout.addRow("Open URLs:", self.url_enabled_checkbox)

        layout.addWidget(url_group)

        # App Configuration Group
        app_group = QGroupBox("Application Settings")
        app_group.setFont(bold_font)
        app_group.setStyleSheet(group_style)
        app_layout = QFormLayout(app_group)
        app_layout.setSpacing(12)

        self.start_minimized_checkbox = QCheckBox()
        self.start_minimized_checkbox.setStyleSheet(checkbox_style)
        self.start_minimized_checkbox.setChecked(settings.value("app/start_minimized", False, type=bool))
        app_layout.addRow("Start Minimized:", self.start_minimized_checkbox)

        self.autostart_checkbox = QCheckBox()
        self.autostart_checkbox.setStyleSheet(checkbox_style)
        self.autostart_checkbox.setChecked(settings.value("app/autostart", False, type=bool))
        app_layout.addRow("Autostart:", self.autostart_checkbox)

        self.simulation_mode_checkbox = QCheckBox()
        self.simulation_mode_checkbox.setStyleSheet(checkbox_style)
        self.simulation_mode_checkbox.setChecked(settings.value("app/simulation_mode", True, type=bool))
        app_layout.addRow("Simulation Mode:", self.simulation_mode_checkbox)

        layout.addWidget(app_group)

        # Add stretch to push content to top
        layout.addStretch()

    def create_analytics_tab(self, colors):
        """Create the Analytics tab"""
        analytics_tab = QWidget()
        analytics_layout = QVBoxLayout(analytics_tab)

        # Create embedded analytics dashboard
        if hasattr(self, 'redis_info') and self.redis_info:
            self.embedded_analytics = AnalyticsDashboard(self.redis_info, self.username, self.password)
            # Remove dialog buttons since we're embedding
            if hasattr(self.embedded_analytics, 'close_button'):
                self.embedded_analytics.close_button.hide()

            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            scroll_area.setWidget(self.embedded_analytics)
            analytics_layout.addWidget(scroll_area)

            # Add refresh button at the bottom
            refresh_button = QPushButton("Refresh Analytics")
            refresh_button.clicked.connect(self.embedded_analytics.refresh_data)
            refresh_button.setStyleSheet(f"""
                QPushButton {{
                    background: {colors['accent_blue']};
                    color: white;
                    border: none;
                    padding: 8px 16px;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 13px;
                    margin: 8px;
                }}
                QPushButton:hover {{
                    background: {colors['hover_bg']};
                    color: {colors['text_primary']};
                }}
            """)
            analytics_layout.addWidget(refresh_button)
        else:
            # Placeholder if no Redis info
            placeholder = QLabel("Analytics will be available once connected to Redis")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet(f"color: {colors['text_muted']}; font-style: italic; padding: 20px;")
            analytics_layout.addWidget(placeholder)

        self.main_tab_widget.addTab(analytics_tab, "Analytics")
        
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
        
        # Analytics is now accessed through the main window tabs
        
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
        """Switch to the configuration tab"""
        # Show the main window and switch to configuration tab
        self.show_and_raise()

        # Find the configuration tab index and switch to it
        for i in range(self.main_tab_widget.count()):
            if self.main_tab_widget.tabText(i) == "Configuration":
                self.main_tab_widget.setCurrentIndex(i)
                break

    def apply_config_settings(self):
        """Apply settings from the configuration tab"""
        # Save settings from the configuration widgets
        settings = QSettings("Busylight", "BusylightController")

        # Save TTS settings
        if hasattr(self, 'tts_enabled_checkbox'):
            settings.setValue("tts/enabled", self.tts_enabled_checkbox.isChecked())

        # Save URL settings
        if hasattr(self, 'url_enabled_checkbox'):
            settings.setValue("url/enabled", self.url_enabled_checkbox.isChecked())

        # Save app settings
        if hasattr(self, 'start_minimized_checkbox'):
            settings.setValue("app/start_minimized", self.start_minimized_checkbox.isChecked())
        if hasattr(self, 'autostart_checkbox'):
            settings.setValue("app/autostart", self.autostart_checkbox.isChecked())
        if hasattr(self, 'simulation_mode_checkbox'):
            settings.setValue("app/simulation_mode", self.simulation_mode_checkbox.isChecked())

        self.add_log(f"[{get_timestamp()}] Settings applied successfully")

        # Restart the Redis worker with new settings
        self.restart_worker()

    def restart_worker(self):
        """Restart the Redis worker with current settings"""
        # Set initialization flag to prevent TTS during restart
        self.is_initializing = True
        
        # Stop existing worker if it exists
        if hasattr(self, 'redis_worker') and self.redis_worker:
            self.redis_worker.stop()
        if hasattr(self, 'worker_thread') and self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait(1000)  # Wait up to 1 second
        
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
        
        # Complete initialization after a delay to allow historical events to load
        QTimer.singleShot(3000, self.complete_initialization)  # 3 second delay
    
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
            # Just print to console if the UI hasn't been created yet or log widget was removed
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
            
        # Get adaptive colors for styling
        colors = get_adaptive_colors()
            
        if connected:
            self.device_label.setText(f"Busylight: {device_name}")
            self.device_label.setStyleSheet(f"color: {colors['accent_green']}; font-weight: 500; font-size: 13px;")
            # Update connection dot
            if hasattr(self, 'connection_dot'):
                self.connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_green']}; font-weight: bold;")
                self.connection_dot.setToolTip(f"Busylight: Connected ({device_name})")
            self.add_log(f"[{get_timestamp()}] Connected to Busylight: {device_name}")
        else:
            # Show red for any disconnected state (including simulation mode)
            if self.light_controller.simulation_mode:
                self.device_label.setText("Busylight: No device found")
                self.device_label.setStyleSheet(f"color: {colors['accent_red']}; font-weight: 500; font-size: 13px;")
                # Update connection dot
                if hasattr(self, 'connection_dot'):
                    self.connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_red']}; font-weight: bold;")
                    self.connection_dot.setToolTip("Busylight: No device found")
                self.add_log(f"[{get_timestamp()}] No Busylight device found")
            else:
                self.device_label.setText("Busylight: No device found")
                self.device_label.setStyleSheet(f"color: {colors['accent_red']}; font-weight: 500; font-size: 13px;")
                # Update connection dot
                if hasattr(self, 'connection_dot'):
                    self.connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_red']}; font-weight: bold;")
                    self.connection_dot.setToolTip("Busylight: No device found")
                self.add_log(f"[{get_timestamp()}] No Busylight device found")

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
                
            # Try to get the most recent status from group-specific status keys
            for group in self.redis_worker.groups:
                status_key = f"status:{group}"
                try:
                    # Get the most recent status event for this group
                    latest = self.redis_worker.redis_client.lindex(status_key, 0)  # Most recent is at index 0
                    if latest:
                        try:
                            data = json.loads(latest)
                            status = data.get('status')
                            if status:
                                self.add_log(f"[{get_timestamp()}] Retrieved last status from Redis ({group}): {status}")
                                # Apply the status
                                self.light_controller.set_status(status)
                                return  # Use the first status found
                        except json.JSONDecodeError as e:
                            self.add_log(f"[{get_timestamp()}] Error parsing Redis message from {group}: {e}")
                            continue
                except Exception as e:
                    self.add_log(f"[{get_timestamp()}] Error accessing status key {status_key}: {e}")
            
            # If we get here, no messages were found in any status key
            self.add_log(f"[{get_timestamp()}] No messages found in any Redis status key")
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
            # Get adaptive colors for styling
            colors = get_adaptive_colors()
            
            if status == "connected":
                self.redis_connection_label.setText("Connected")
                self.redis_connection_label.setStyleSheet(f"color: {colors['accent_green']}; font-weight: 500; font-size: 13px;")
                # Update Redis connection dot
                if hasattr(self, 'redis_connection_dot'):
                    self.redis_connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_green']}; font-weight: bold;")
                    self.redis_connection_dot.setToolTip("Connected")
                self.add_log(f"[{get_timestamp()}] Redis connected")
            else:
                self.redis_connection_label.setText("Disconnected")
                self.redis_connection_label.setStyleSheet(f"color: {colors['accent_red']}; font-weight: 500; font-size: 13px;")
                # Update Redis connection dot
                if hasattr(self, 'redis_connection_dot'):
                    self.redis_connection_dot.setStyleSheet(f"font-size: 18px; color: {colors['accent_red']}; font-weight: bold;")
                    self.redis_connection_dot.setToolTip("Disconnected")
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
        zoho_ticket_url = ticket_info.get('zoho_ticket_url', '')
        group = ticket_info.get('group', '')

        self.add_log(f"[{get_timestamp()}] Ticket #{ticket_id} received")

        if summary:
            self.add_log(f"[{get_timestamp()}] Summary: {summary}")
            # Handle text-to-speech if enabled
            self.speak_ticket_summary(summary)

        if zoho_ticket_url:
            self.add_log(f"[{get_timestamp()}] Zoho ticket URL: {zoho_ticket_url}")
            # Handle URL opening if enabled and user belongs to the group
            if self.redis_info and group in self.redis_info.get('groups', []):
                self.open_ticket_url(zoho_ticket_url)
            else:
                self.add_log(f"[{get_timestamp()}] URL popup skipped - user not a member of group '{group}'")
    
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
    
    def speak_group_status_event(self, group, status, data):
        """Speak group status events using text-to-speech"""
        # Skip TTS during app initialization to avoid speaking historical events
        if self.is_initializing:
            return
            
        # Load TTS settings
        settings = QSettings("Busylight", "BusylightController")
        tts_enabled = settings.value("tts/enabled", False, type=bool)
        
        if not tts_enabled:
            return
        
        try:
            # Create a human-readable message for the status event
            status_name = self.light_controller.COLOR_NAMES.get(status, status.title())
            source = data.get('source', 'Unknown')
            reason = data.get('reason', '')
            
            # Build the TTS message
            if reason:
                tts_message = f"Group {group} status changed to {status_name} by {source}. Reason: {reason}"
            else:
                tts_message = f"Group {group} status changed to {status_name} by {source}"
            
            # Use platform-specific approaches for safer TTS
            system = platform.system()
            
            if system == "Darwin":  # macOS
                # Use macOS say command directly with list arguments
                subprocess.Popen(["say", tts_message], shell=False)
                self.add_log(f"[{get_timestamp()}] Speaking group status event using macOS say command")
            
            elif system == "Windows":
                # Use PowerShell with safer argument passing
                ps_script = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).Speak('{0}')"
                ps_script = ps_script.format(tts_message.replace("'", "''"))  # PowerShell escape single quotes
                subprocess.Popen(["powershell", "-Command", ps_script], shell=False)
                self.add_log(f"[{get_timestamp()}] Speaking group status event using Windows speech")
            
            else:  # Linux and other platforms - attempt to use festival
                # Safer approach for Linux using pipes instead of shell
                process = subprocess.Popen(["festival", "--tts"], stdin=subprocess.PIPE, shell=False)
                process.communicate(tts_message.encode())
                self.add_log(f"[{get_timestamp()}] Speaking group status event using festival")
                
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error executing TTS for group status event: {e}")
    
    def open_ticket_url(self, url):
        """Open the ticket URL using a secure method"""
        # Load URL settings
        settings = QSettings("Busylight", "BusylightController")
        url_enabled = settings.value("url/enabled", False, type=bool)

        if not url_enabled:
            self.add_log(f"[{get_timestamp()}] URL opening is disabled in configuration")
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
        
        # Trigger text-to-speech announcement only for groups the user is a member of
        if self.redis_info and group in self.redis_info.get('groups', []):
            self.speak_group_status_event(group, status, data)
        
        # Update the UI widget for this group (full widget for user's groups)
        if group in self.group_widgets:
            widgets = self.group_widgets[group]
            status_label = widgets['status_label']
            event_history_text = widgets['event_history_text']
            
            # Update status text and color
            status_name = self.light_controller.COLOR_NAMES.get(status, status.title())
            status_label.setText(status_name)
            
            # Get adaptive colors for styling
            colors = get_adaptive_colors()
            
            # Set modern background color based on status
            if status in self.light_controller.COLOR_MAP:
                r, g, b = self.light_controller.COLOR_MAP[status]
                if status == 'off':
                    status_label.setStyleSheet(f"""
                        font-size: 11px;
                        font-weight: 700;
                        padding: 12px;
                        border-radius: 16px;
                        min-width: 90px;
                        min-height: 90px;
                        max-width: 90px;
                        max-height: 90px;
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {colors['bg_secondary']}, stop:1 {colors['bg_tertiary']});
                        border: 2px solid {colors['border_secondary']};
                        color: {colors['text_muted']};
                    """)
                else:
                    # Create a subtle gradient for active statuses
                    # Determine text color based on brightness of status color
                    brightness = (r + g + b) / 3
                    text_color = "#000000" if brightness > 128 else "#ffffff"
                    
                    status_label.setStyleSheet(f"""
                        font-size: 11px;
                        font-weight: 700;
                        padding: 12px;
                        border-radius: 16px;
                        min-width: 90px;
                        min-height: 90px;
                        max-width: 90px;
                        max-height: 90px;
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgb({min(r+30, 255)}, {min(g+30, 255)}, {min(b+30, 255)}), 
                            stop:1 rgb({r}, {g}, {b}));
                        border: 2px solid rgb({max(r-40, 0)}, {max(g-40, 0)}, {max(b-40, 0)});
                        color: {text_color};
                    """)
            else:
                # Default styling for unknown status
                status_label.setStyleSheet(f"""
                    font-size: 11px;
                    font-weight: 700;
                    padding: 12px;
                    border-radius: 16px;
                    min-width: 90px;
                    min-height: 90px;
                    max-width: 90px;
                    max-height: 90px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {colors['bg_secondary']}, stop:1 {colors['bg_tertiary']});
                    border: 2px solid {colors['border_secondary']};
                    color: {colors['text_muted']};
                """)
            
            # Update timestamp
            timestamp_label = widgets['timestamp_label']
            timestamp_label.setText(f"Last Update: {get_timestamp()}")
            
            # Parse and display event information in the group's history
            self.parse_and_display_event(group, status, data, event_history_text)

        # Also update compact widget for this group if it exists (for all groups overview)
        elif hasattr(self, 'all_group_widgets') and group in self.all_group_widgets:
            compact_widgets = self.all_group_widgets[group]
            compact_status_label = compact_widgets['status_label']

            # Update compact status text and color
            status_name = self.light_controller.COLOR_NAMES.get(status, status.title())
            compact_status_label.setText(status_name)

            # Get adaptive colors for styling
            colors = get_adaptive_colors()

            # Set compact background color based on status
            if status in self.light_controller.COLOR_MAP:
                r, g, b = self.light_controller.COLOR_MAP[status]
                if status == 'off':
                    compact_status_label.setStyleSheet(f"""
                        font-size: 8px;
                        font-weight: 600;
                        padding: 6px;
                        border-radius: 12px;
                        min-width: 50px;
                        min-height: 30px;
                        max-width: 50px;
                        max-height: 30px;
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 {colors['bg_secondary']}, stop:1 {colors['bg_tertiary']});
                        border: 1px solid {colors['border_secondary']};
                        color: {colors['text_muted']};
                    """)
                else:
                    # Create a subtle gradient for active statuses
                    brightness = (r + g + b) / 3
                    text_color = "#000000" if brightness > 128 else "#ffffff"

                    compact_status_label.setStyleSheet(f"""
                        font-size: 8px;
                        font-weight: 600;
                        padding: 6px;
                        border-radius: 12px;
                        min-width: 50px;
                        min-height: 30px;
                        max-width: 50px;
                        max-height: 30px;
                        background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                            stop:0 rgb({min(r+30, 255)}, {min(g+30, 255)}, {min(b+30, 255)}),
                            stop:1 rgb({r}, {g}, {b}));
                        border: 1px solid rgb({max(r-40, 0)}, {max(g-40, 0)}, {max(b-40, 0)});
                        color: {text_color};
                    """)
            else:
                # Default styling for unknown status
                compact_status_label.setStyleSheet(f"""
                    font-size: 8px;
                    font-weight: 600;
                    padding: 6px;
                    border-radius: 12px;
                    min-width: 50px;
                    min-height: 30px;
                    max-width: 50px;
                    max-height: 30px;
                    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                        stop:0 {colors['bg_secondary']}, stop:1 {colors['bg_tertiary']});
                    border: 1px solid {colors['border_secondary']};
                    color: {colors['text_muted']};
                """)

        else:
            # Fallback logging if no UI widget found
            print(f"[{get_timestamp()}] Group '{group}' status updated: {status} (no UI widget found)")
    
    def parse_and_display_event(self, group, status, data, event_history_text):
        """Parse incoming event data and display it in the group's event history"""
        try:
            # Create a formatted event message
            timestamp = data.get('timestamp', get_timestamp())
            source = data.get('source', 'Unknown')
            reason = data.get('reason', '')
            
            # Format the event message
            if reason:
                event_message = f"{timestamp} - {status.upper()} by {source}\nReason: {reason}\n"
            else:
                event_message = f"{timestamp} - {status.upper()} by {source}\n"
            
            # Add the new event to the top of the history
            current_text = event_history_text.toPlainText()
            new_text = event_message + current_text
            
            # Limit the history to prevent it from growing too large
            lines = new_text.split('\n')
            if len(lines) > 20:  # Keep only last 20 lines
                lines = lines[:20]
                new_text = '\n'.join(lines)
            
            # Update the event history display
            event_history_text.setPlainText(new_text)
            
            # Auto-scroll to top to show the newest event
            scrollbar = event_history_text.verticalScrollBar()
            scrollbar.setValue(0)
            
        except Exception as e:
            # If parsing fails, just add a simple message
            simple_message = f"{get_timestamp()} - {status.upper()}\n"
            current_text = event_history_text.toPlainText()
            event_history_text.setPlainText(simple_message + current_text)

    def on_group_clicked(self, group):
        """Handle group status widget click event"""
        dialog = StatusChangeDialog(current_group=group, parent=self)
        if dialog.exec() == QDialog.Accepted:
            result = dialog.get_result()
            if result:
                # Log the status change request
                self.add_log(f"[{get_timestamp()}] Status change requested for group '{result['group']}': {result['action']} - {result['reason']}")
                
                # The API call is made in the dialog's submit_to_api method
                # The real event will come back from Redis, so no need to simulate locally
                # self.simulate_status_change(result['group'], result['action'], result['reason'])  # Removed to prevent duplicates
    
    # simulate_status_change method removed to prevent duplicate events
    # The real events now come from Redis after API submission

    def create_full_group_widget(self, group, colors):
        """Create a full-featured group widget with event history and clickability"""
        group_widget = QGroupBox(f"Group: {group}")

        # Set bold font directly using Qt's font system
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(12)  # Larger size for prominence
        group_widget.setFont(bold_font)

        group_widget.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['hover_bg']});
                border: 2px solid {colors['accent_blue']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        group_layout = QHBoxLayout()
        group_layout.setSpacing(16)
        group_layout.setContentsMargins(0, 0, 0, 0)

        # Left side: Status display area
        status_container = QWidget()
        status_container.setFixedWidth(130)  # Fixed width to ensure consistent alignment
        status_container_layout = QVBoxLayout(status_container)
        status_container_layout.setContentsMargins(0, 0, 0, 0)
        status_container_layout.setSpacing(8)
        status_container_layout.setAlignment(Qt.AlignCenter)

        # Square status color bar with modern styling
        status_label = QLabel("Green\n(Normal)")
        # Apply default 'normal' styling using the existing color system
        r, g, b = self.light_controller.COLOR_MAP['normal']
        brightness = (r + g + b) / 3
        text_color = "#000000" if brightness > 128 else "#ffffff"
        status_label.setStyleSheet(f"""
            font-size: 11px;
            font-weight: 700;
            padding: 12px;
            border-radius: 16px;
            min-width: 90px;
            min-height: 90px;
            max-width: 90px;
            max-height: 90px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgb({min(r+30, 255)}, {min(g+30, 255)}, {min(b+30, 255)}),
                stop:1 rgb({r}, {g}, {b}));
            border: 2px solid rgb({max(r-40, 0)}, {max(g-40, 0)}, {max(b-40, 0)});
            color: {text_color};
        """)
        status_label.setAlignment(Qt.AlignCenter)
        status_label.setFixedSize(90, 90)
        status_container_layout.addWidget(status_label, alignment=Qt.AlignCenter)

        # Timestamp label
        timestamp_label = QLabel("Last Update: Never")
        timestamp_label.setStyleSheet(f"color: {colors['text_muted']}; font-size: 9px; font-style: italic;")
        timestamp_label.setAlignment(Qt.AlignCenter)
        status_container_layout.addWidget(timestamp_label, alignment=Qt.AlignCenter)

        group_layout.addWidget(status_container)

        # Right side: Event history display
        history_container = QWidget()
        history_layout = QVBoxLayout(history_container)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(8)

        # Event history label with modern styling
        event_history_label = QLabel("Event History")
        event_history_label.setStyleSheet(f"""
            font-weight: 600;
            color: {colors['text_primary']};
            font-size: 12px;
            padding: 4px 0;
        """)
        history_layout.addWidget(event_history_label)

        # Event history text area with modern styling
        event_history_text = QTextEdit()
        event_history_text.setReadOnly(True)
        event_history_text.setMinimumHeight(90)
        event_history_text.setStyleSheet(f"""
            font-size: 10px;
            font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
            background: {colors['input_bg']};
            border: 1px solid {colors['input_border']};
            border-radius: 8px;
            padding: 8px;
            color: {colors['text_secondary']};
            selection-background-color: {colors['accent_blue']};
            selection-color: {colors['bg_primary']};
        """)
        history_layout.addWidget(event_history_text)

        group_layout.addWidget(history_container)

        group_widget.setLayout(group_layout)

        # Make the group widget clickable with tactile effect
        def create_click_handler(group_name, widget):
            def mouse_press_event(event):
                # Add pressed effect while preserving bold title
                widget.setStyleSheet(f"""
                    QGroupBox {{
                        border: 2px solid {colors['accent_blue']};
                        border-radius: 12px;
                        margin: 7px;
                        padding: 16px;
                        background-color: {colors['hover_bg']};
                    }}
                    QGroupBox::title {{
                        subcontrol-origin: margin;
                        left: 16px;
                        padding: 0 8px 0 8px;
                        color: {colors['text_primary']};
                        font-weight: 800;
                        font-size: 16px;
                    }}
                """)

                # Ensure the font remains bold
                bold_font = QFont()
                bold_font.setBold(True)
                bold_font.setPointSize(12)
                widget.setFont(bold_font)

                QApplication.processEvents()  # Force immediate update

                # Small delay for tactile effect
                QTimer.singleShot(100, lambda: self.complete_group_click(group_name, widget))

            return mouse_press_event

        group_widget.mousePressEvent = create_click_handler(group, group_widget)

        # Store references for updates
        self.group_widgets[group] = {
            'widget': group_widget,
            'status_label': status_label,
            'timestamp_label': timestamp_label,
            'event_history_text': event_history_text
        }

        return group_widget

    def create_compact_group_widget(self, group, colors):
        """Create a display-only compact group widget showing status indicator"""
        compact_widget = QGroupBox(group)
        compact_widget.setFixedSize(120, 80)

        # Disable interaction to make it clear this is display-only
        compact_widget.setEnabled(True)  # Keep enabled for visual updates but no click handling
        compact_widget.setCursor(Qt.ArrowCursor)  # Normal cursor, not pointer

        # Set smaller font for compact view
        compact_font = QFont()
        compact_font.setBold(True)
        compact_font.setPointSize(9)
        compact_widget.setFont(compact_font)

        # Style without hover effects to indicate display-only
        compact_widget.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 8px;
                margin: 4px;
                padding: 8px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 1px solid {colors['border_secondary']};
                opacity: 0.9;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: {colors['text_muted']};
                font-weight: 600;
                font-size: 9px;
            }}
        """)

        compact_layout = QVBoxLayout(compact_widget)
        compact_layout.setContentsMargins(4, 8, 4, 4)
        compact_layout.setSpacing(4)
        compact_layout.setAlignment(Qt.AlignCenter)

        # Small status indicator
        status_indicator = QLabel("Normal")
        # Apply default 'normal' styling using the existing color system
        r, g, b = self.light_controller.COLOR_MAP['normal']
        brightness = (r + g + b) / 3
        text_color = "#000000" if brightness > 128 else "#ffffff"
        status_indicator.setStyleSheet(f"""
            font-size: 8px;
            font-weight: 600;
            padding: 6px;
            border-radius: 12px;
            min-width: 50px;
            min-height: 30px;
            max-width: 50px;
            max-height: 30px;
            background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 rgb({min(r+30, 255)}, {min(g+30, 255)}, {min(b+30, 255)}),
                stop:1 rgb({r}, {g}, {b}));
            border: 1px solid rgb({max(r-40, 0)}, {max(g-40, 0)}, {max(b-40, 0)});
            color: {text_color};
        """)
        status_indicator.setAlignment(Qt.AlignCenter)
        status_indicator.setFixedSize(50, 30)
        compact_layout.addWidget(status_indicator, alignment=Qt.AlignCenter)

        # Explicitly disable mouse interaction to ensure display-only behavior
        def ignore_mouse_events(event):
            """Ignore all mouse events to prevent any interaction"""
            event.ignore()

        compact_widget.mousePressEvent = ignore_mouse_events
        compact_widget.mouseReleaseEvent = ignore_mouse_events
        compact_widget.mouseDoubleClickEvent = ignore_mouse_events

        # Store reference for status updates (but no event history)
        if not hasattr(self, 'all_group_widgets'):
            self.all_group_widgets = {}

        self.all_group_widgets[group] = {
            'widget': compact_widget,
            'status_label': status_indicator
        }

        return compact_widget

    def complete_group_click(self, group, widget):
        """Complete the group click with tactile effect"""
        # Get adaptive colors for styling
        colors = get_adaptive_colors()
        
        # Restore normal appearance with bold title
        widget.setStyleSheet(f"""
            QGroupBox {{
                border: none;
                border-radius: 12px;
                margin: 8px;
                padding: 16px;
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['bg_secondary']});
                border: 2px solid {colors['border_secondary']};
            }}
            QGroupBox:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 {colors['bg_primary']}, stop:1 {colors['hover_bg']});
                border: 2px solid {colors['accent_blue']};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 16px;
                padding: 0 8px 0 8px;
                color: {colors['text_primary']};
                font-weight: 800;
                font-size: 16px;
            }}
        """)
        
        # Ensure the font remains bold
        bold_font = QFont()
        bold_font.setBold(True)
        bold_font.setPointSize(12)
        widget.setFont(bold_font)
        
        # Open the dialog
        self.on_group_clicked(group)

    def start_redis_worker(self):
        """Start the Redis worker thread"""
        if self.redis_info:
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

    def complete_initialization(self):
        """Complete initialization tasks after the UI is ready"""
        self.is_initializing = False
        self.add_log(f"[{get_timestamp()}] Initialization complete - TTS now active for new events")

    def show_analytics_dashboard(self):
        """Switch to the analytics tab"""
        # Show the main window and switch to analytics tab
        self.show_and_raise()

        # Find the analytics tab index and switch to it
        for i in range(self.main_tab_widget.count()):
            if self.main_tab_widget.tabText(i) == "Analytics":
                self.main_tab_widget.setCurrentIndex(i)
                break
    
    def restart_worker(self):
        """Restart the Redis worker with current settings"""
        # Set initialization flag to prevent TTS during restart
        self.is_initializing = True
        
        # Stop existing worker if it exists
        if hasattr(self, 'redis_worker') and self.redis_worker:
            self.redis_worker.stop()
        if hasattr(self, 'worker_thread') and self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait(1000)  # Wait up to 1 second
        
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
        
        # Complete initialization after a delay to allow historical events to load
        QTimer.singleShot(3000, self.complete_initialization)  # 3 second delay

# Main application
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep app running when window is closed
    
    # Create default icon if needed
    create_default_icon()
    
    # Set application icon
    icon_path = get_resource_path("icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
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
    icon_path = get_resource_path("icon.png")
    if not os.path.exists(icon_path):
        # Create a simple colored icon
        pixmap = QPixmap(128, 128)
        pixmap.fill(QColor(0, 255, 0))  # Green
        
        # Save it - try to save in the current directory for development
        try:
            pixmap.save("icon.png")
            print(f"[{get_timestamp()}] Created default icon.png")
        except Exception as e:
            print(f"[{get_timestamp()}] Could not create default icon: {e}")

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
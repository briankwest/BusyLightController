#!/usr/bin/env python3
# Author: Shane Harrell (GUI by Assistant)

import json
import sys
import os
import platform
import socket
import signal
from datetime import datetime
import time
import hashlib
import redis
import requests
import dotenv
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                            QLabel, QPushButton, QComboBox, QSystemTrayIcon,
                            QMenu, QTextEdit, QHBoxLayout, QGroupBox, QLineEdit,
                            QDialog, QDialogButtonBox, QFormLayout, QCheckBox,
                            QMessageBox, QScrollArea, QTabWidget,
                            QSplitter, QListWidget, QListWidgetItem, QColorDialog)
from PySide6.QtCore import Qt, QTimer, Signal as pyqtSignal, QObject, QThread, QSettings, QRect, QPoint, QSize
from PySide6.QtGui import QIcon, QColor, QPixmap, QFont, QPainter, QPen, QTextCursor, QBrush, QPolygon
from PySide6.QtWidgets import QSlider
import webbrowser
from gtts import gTTS
import pygame
from io import BytesIO
import logging
import logging.handlers
from pathlib import Path

# Application version - increment this with each code change
APP_VERSION = "1.2.0"

# User-Agent for API requests
USER_AGENT = f"BusylightController/{APP_VERSION}"

# UI Text Constants
APPLY_SETTINGS_BUTTON_TEXT = "Apply Settings"
APPLY_SETTINGS_BUTTON_TEXT_UPDATING = "Applying Settings..."

# User presence status constants (display only, does not affect busylight)
USER_STATUS_AVAILABLE = "available"
USER_STATUS_BUSY = "busy"
USER_STATUS_AWAY = "away"
USER_STATUS_BREAK = "break"
USER_STATUS_OFFLINE = "offline"

# User status display colors (for UI dots, not for busylight hardware)
USER_STATUS_COLORS = {
    'available': '#00ff00',  # Green
    'busy': '#ff0000',       # Red
    'away': '#ffff00',       # Yellow
    'break': '#ff9800',      # Orange
    'offline': '#888888'     # Gray
}

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
from busylight.speed import Speed

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

class SectionedListWidget(QListWidget):
    """A QListWidget that prevents dragging items between sections.

    Items must have their section stored in Qt.UserRole + 1 data.
    Section headers should have Qt.NoItemFlags to prevent selection/dragging.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._dragged_item = None
        self._dragged_section = None

    def startDrag(self, supportedActions):
        """Remember which section the dragged item belongs to"""
        item = self.currentItem()
        if item:
            self._dragged_item = item
            self._dragged_section = item.data(Qt.UserRole + 1)
        super().startDrag(supportedActions)

    def dropEvent(self, event):
        """Only allow drops within the same section"""
        if self._dragged_section is None:
            event.ignore()
            return

        # Find the drop position
        drop_pos = event.position().toPoint()
        drop_item = self.itemAt(drop_pos)

        # Determine the target section
        target_section = None
        if drop_item:
            target_section = drop_item.data(Qt.UserRole + 1)
            # If dropping on a header (no section data), find the section below
            if target_section is None:
                drop_row = self.row(drop_item)
                # Look at the next item to determine section
                for i in range(drop_row + 1, self.count()):
                    next_item = self.item(i)
                    next_section = next_item.data(Qt.UserRole + 1)
                    if next_section:
                        target_section = next_section
                        break
        else:
            # Dropped at end of list - find the section of the last item
            if self.count() > 0:
                last_item = self.item(self.count() - 1)
                target_section = last_item.data(Qt.UserRole + 1)

        # Only allow drop if same section
        if target_section == self._dragged_section:
            super().dropEvent(event)
        else:
            event.ignore()

        # Clear drag state
        self._dragged_item = None
        self._dragged_section = None


# QSS (Qt Style Sheet) Helper Functions
# These functions provide reusable styling patterns to reduce code duplication

def qss_dialog_base(colors):
    """Base dialog styling with background and text colors"""
    return f"""
        QDialog {{
            background-color: {colors['bg_primary']};
            color: {colors['text_primary']};
        }}
        QWidget {{
            background-color: {colors['bg_primary']};
            color: {colors['text_primary']};
        }}
    """

def qss_groupbox_gradient(colors, title_size=16):
    """Gradient groupbox with title styling"""
    return f"""
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
            font-size: {title_size}px;
        }}
    """

def qss_groupbox_simple(colors):
    """Simple groupbox without gradient"""
    return f"""
        QGroupBox {{
            border: 2px solid {colors['border_secondary']};
            border-radius: 8px;
            padding: 16px;
            background: {colors['bg_secondary']};
        }}
    """

def qss_button_primary(colors, padding="8px 16px", border_radius=6):
    """Primary action button (blue)"""
    return f"""
        QPushButton {{
            background: {colors['accent_blue']};
            color: white;
            border: none;
            padding: {padding};
            border-radius: {border_radius}px;
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
    """

def qss_lineedit(colors, padding="8px 12px", border_radius=8):
    """Text input field with focus state"""
    return f"""
        QLineEdit {{
            padding: {padding};
            border: 1px solid {colors['input_border']};
            border-radius: {border_radius}px;
            background: {colors['input_bg']};
            font-size: 13px;
            color: {colors['text_secondary']};
        }}
        QLineEdit:focus {{
            border-color: {colors['accent_blue']};
            outline: none;
        }}
    """

def qss_combobox_full(colors, padding="8px 12px", border_radius=8):
    """Full combobox with dropdown arrow and item view styling"""
    return f"""
        QComboBox {{
            padding: {padding};
            border: 1px solid {colors['input_border']};
            border-radius: {border_radius}px;
            background: {colors['input_bg']};
            font-size: 13px;
            color: {colors['text_secondary']};
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
        }}
        QComboBox QAbstractItemView {{
            background: {colors['input_bg']};
            border: 1px solid {colors['input_border']};
            selection-background-color: {colors['accent_blue']};
            selection-color: {colors['bg_primary']};
            color: {colors['text_primary']};
        }}
    """

def qss_combobox_simple(colors, padding="8px 12px", border_radius=8):
    """Simple combobox without custom arrow"""
    return f"""
        QComboBox {{
            padding: {padding};
            border: 1px solid {colors['input_border']};
            border-radius: {border_radius}px;
            background: {colors['input_bg']};
            font-size: 13px;
            color: {colors['text_secondary']};
        }}
    """

def qss_slider_horizontal(colors):
    """Horizontal slider with custom handle"""
    return f"""
        QSlider::groove:horizontal {{
            border: 1px solid {colors['input_border']};
            height: 8px;
            background: {colors['input_bg']};
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {colors['accent_blue']};
            border: none;
            width: 18px;
            margin: -5px 0;
            border-radius: 9px;
        }}
    """

def qss_checkbox_indicator(colors, indicator_size=18, border_width=2):
    """Checkbox with custom indicator styling"""
    return f"""
        QCheckBox {{
            font-size: 14px;
            color: {colors['text_primary']};
        }}
        QCheckBox::indicator {{
            width: {indicator_size}px;
            height: {indicator_size}px;
            border: {border_width}px solid {colors['border_secondary']};
            border-radius: 4px;
            background: {colors['input_bg']};
        }}
        QCheckBox::indicator:checked {{
            background: {colors['accent_blue']};
            border-color: {colors['accent_blue']};
        }}
    """

def get_available_english_voices():
    """Get list of available English TTS accents for gTTS"""
    # gTTS uses Google's TTS API with different accents via TLD (top-level domain)
    return [
        {'id': 'en-us', 'name': 'English (US)'},
        {'id': 'en-uk', 'name': 'English (UK)'},
        {'id': 'en-au', 'name': 'English (Australia)'},
        {'id': 'en-in', 'name': 'English (India)'},
        {'id': 'en-ca', 'name': 'English (Canada)'},
        {'id': 'en-za', 'name': 'English (South Africa)'},
        {'id': 'en-ie', 'name': 'English (Ireland)'},
        {'id': 'en-ng', 'name': 'English (Nigeria)'},
    ]

def get_log_directory():
    """Get platform-specific log directory and ensure it exists"""
    system = platform.system()

    if system == "Darwin":  # macOS
        log_dir = Path.home() / "Library" / "Logs" / "Busylight"
    elif system == "Windows":
        log_dir = Path(os.getenv("APPDATA")) / "Busylight" / "Logs"
    else:  # Linux and others
        log_dir = Path.home() / ".local" / "share" / "Busylight" / "logs"

    # Create directory if it doesn't exist
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir

def get_log_file_path():
    """Get the full path to the log file"""
    return get_log_directory() / "BusylightController.log"

class QtLogHandler(logging.Handler):
    """Custom log handler that emits Qt signals for UI updates"""

    def __init__(self):
        super().__init__()
        self.signal_emitter = None

    def set_signal_emitter(self, emitter):
        """Set the signal emitter (must be called from main thread)"""
        self.signal_emitter = emitter

    def emit(self, record):
        """Emit log record to Qt signal"""
        if self.signal_emitter:
            try:
                msg = self.format(record)
                level_name = record.levelname
                self.signal_emitter.log_message.emit(msg, level_name)
            except Exception:
                self.handleError(record)

class APIClient:
    """Centralized API client for status submissions"""

    def __init__(self, username, password, logger_callback=None):
        """
        Initialize API client

        Args:
            username: API username for authentication
            password: API password for authentication
            logger_callback: Optional callback function for logging (receives message string)
        """
        self.username = username
        self.password = password
        self.logger_callback = logger_callback
        self.api_base_url = "https://busylight.signalwire.me"

    def submit_status(self, status, group, source, reason=None, url=None):
        """
        Submit status update to API

        Args:
            status: Status value (e.g., 'available', 'busy', 'away')
            group: Group/queue name
            source: Source identifier (username)
            reason: Optional reason text
            url: Optional URL to include (will be auto-prefixed with https://)

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            # Prepare API request
            api_url = f"{self.api_base_url}/api/status"

            payload = {
                'status': status,
                'source': source,
                'group': group,
                'timestamp': get_timestamp()
            }

            # Add optional fields
            if reason:
                payload['reason'] = reason

            if url:
                # Auto-prepend https:// if missing
                if not url.startswith(('http://', 'https://')):
                    url = f'https://{url}'
                payload['busylight_pop_url'] = url

            headers = {
                'Content-Type': 'application/json',
                'User-Agent': USER_AGENT
            }

            # Make API call with authentication
            response = requests.post(
                api_url,
                json=payload,
                headers=headers,
                auth=(self.username, self.password),
                timeout=10
            )

            # Check response
            if response.status_code == 200:
                success_msg = f"Status updated successfully for group '{group}'"
                if self.logger_callback:
                    self.logger_callback(f"[{get_timestamp()}] API: {success_msg}")
                return True, success_msg
            else:
                # Try to parse error from response
                try:
                    error_data = response.json()
                    error_msg = error_data.get('error', f"HTTP {response.status_code}")
                except:
                    error_msg = f"HTTP {response.status_code}"

                if self.logger_callback:
                    self.logger_callback(f"[{get_timestamp()}] API Error: {error_msg}")
                return False, f"Failed to update status: {error_msg}"

        except requests.exceptions.Timeout:
            error_msg = "Request timed out. Please try again."
            if self.logger_callback:
                self.logger_callback(f"[{get_timestamp()}] API Error: Request timeout")
            return False, error_msg

        except requests.exceptions.ConnectionError:
            error_msg = "Connection failed. Check your network connection."
            if self.logger_callback:
                self.logger_callback(f"[{get_timestamp()}] API Error: Connection failed")
            return False, error_msg

        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            if self.logger_callback:
                self.logger_callback(f"[{get_timestamp()}] API Error: {str(e)}")
            return False, error_msg

class LogSignalEmitter(QObject):
    """QObject for emitting log signals"""
    log_message = pyqtSignal(str, str)  # message, level

class LogWidget(QTextEdit):
    """Custom QTextEdit widget for displaying color-coded logs"""

    MAX_LINES = 1000  # Maximum lines to keep in memory

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QTextEdit.NoWrap)
        self.line_count = 0

        # Enable rich text for color-coded logs
        self.setAcceptRichText(True)

    def add_log_message(self, message, level):
        """Add a color-coded log message to the widget"""
        # Get color based on log level
        color = self.get_level_color(level)

        # Create HTML formatted message
        html_message = f'<span style="color: {color};">{self.escape_html(message)}</span><br>'

        # Append to widget
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html_message)

        # Increment line count
        self.line_count += 1

        # Trim if we exceed max lines
        if self.line_count > self.MAX_LINES:
            self.trim_to_max_lines()

        # Auto-scroll to bottom
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def get_level_color(self, level):
        """Get color for log level based on dark/light mode"""
        dark_mode = is_dark_mode()

        colors = {
            'DEBUG': '#888888' if dark_mode else '#6c757d',
            'INFO': '#ffffff' if dark_mode else '#202124',
            'WARNING': '#ffa726' if dark_mode else '#ff9800',
            'ERROR': '#ef5350' if dark_mode else '#dc3545',
        }

        return colors.get(level, '#ffffff' if dark_mode else '#202124')

    def escape_html(self, text):
        """Escape HTML special characters"""
        return (text
                .replace('&', '&amp;')
                .replace('<', '&lt;')
                .replace('>', '&gt;')
                .replace('"', '&quot;')
                .replace("'", '&#39;'))

    def trim_to_max_lines(self):
        """Remove oldest lines to keep within MAX_LINES limit"""
        # Get all text
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.Start)

        # Count lines and remove excess from top
        lines_to_remove = self.line_count - self.MAX_LINES

        for _ in range(lines_to_remove):
            cursor.select(QTextCursor.SelectionType.LineUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # Remove the newline

        self.line_count = self.MAX_LINES

    def clear_logs(self):
        """Clear all logs from the widget"""
        self.clear()
        self.line_count = 0

    def get_all_text(self):
        """Get all log text (plain text, no HTML)"""
        return self.toPlainText()

# Global log handler and emitter
_qt_log_handler = None
_log_signal_emitter = None

def setup_logging():
    """Configure application logging with rotating file handler"""
    global _qt_log_handler, _log_signal_emitter

    # Create logger
    logger = logging.getLogger("BusylightController")
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create rotating file handler (5MB max, 1 backup)
    log_file = get_log_file_path()
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,  # 5MB
        backupCount=1,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)

    # Add file handler
    logger.addHandler(file_handler)

    # Create Qt handler for UI updates
    _qt_log_handler = QtLogHandler()
    _qt_log_handler.setLevel(logging.DEBUG)
    _qt_log_handler.setFormatter(formatter)
    logger.addHandler(_qt_log_handler)

    # Create signal emitter
    _log_signal_emitter = LogSignalEmitter()
    _qt_log_handler.set_signal_emitter(_log_signal_emitter)

    # Log startup info
    logger.info(f"BusylightController v{APP_VERSION} starting on {platform.system()} {platform.release()}")
    logger.info(f"Log file: {log_file}")

    return logger, _log_signal_emitter

def get_logger():
    """Get the application logger"""
    return logging.getLogger("BusylightController")

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

        # Set up a timer to check if app is quitting (for Ctrl+C handling)
        self.quit_check_timer = QTimer(self)
        self.quit_check_timer.timeout.connect(self.check_if_quitting)
        self.quit_check_timer.start(100)  # Check every 100ms
        
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
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

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
            "User-Agent": USER_AGENT
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

    def check_if_quitting(self):
        """Check if the application is quitting and close dialog if so"""
        app = QApplication.instance()
        if app and app.property("quitting_from_signal"):
            print(f"[{get_timestamp()}] Login dialog closing due to quit signal")
            self.quit_check_timer.stop()
            self.reject()

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
        tts_layout.setLabelAlignment(Qt.AlignLeft)
        tts_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        tts_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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

        # Speech rate checkbox (Fast/Slow)
        self.tts_rate_label = QLabel("Slow Speech:")
        self.tts_rate_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_slow_checkbox = QCheckBox()
        self.tts_slow_checkbox.setChecked(self.settings.value("tts/slow", False, type=bool))
        self.tts_slow_checkbox.setStyleSheet(f"""
            QCheckBox {{
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border: 1px solid {colors['input_border']};
                border-radius: 4px;
                background: {colors['input_bg']};
            }}
            QCheckBox::indicator:checked {{
                background: {colors['accent_blue']};
                border-color: {colors['accent_blue']};
            }}
        """)

        # Volume slider
        self.tts_volume_label = QLabel("Volume:")
        self.tts_volume_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_volume_slider = QSlider(Qt.Horizontal)
        self.tts_volume_slider.setRange(0, 100)
        self.tts_volume_slider.setValue(int(self.settings.value("tts/volume", 0.9, type=float) * 100))
        self.tts_volume_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {colors['input_border']};
                height: 8px;
                background: {colors['input_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent_blue']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
        """)

        # Voice selection dropdown
        self.tts_voice_label = QLabel("Voice:")
        self.tts_voice_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_voice_combo = QComboBox()
        self.tts_voice_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
        """)

        # Populate voices
        english_voices = get_available_english_voices()
        saved_voice_id = self.settings.value("tts/voice_id", None)
        selected_index = 0

        for idx, voice in enumerate(english_voices):
            self.tts_voice_combo.addItem(voice['name'], voice['id'])
            if saved_voice_id and voice['id'] == saved_voice_id:
                selected_index = idx

        if english_voices:
            self.tts_voice_combo.setCurrentIndex(selected_index)

        # Custom test text input
        self.tts_test_text_label = QLabel("Test Text:")
        self.tts_test_text_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_test_text_input = QLineEdit()
        self.tts_test_text_input.setPlaceholderText("Enter text to test voice (optional)")
        self.tts_test_text_input.setStyleSheet(f"""
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

        # Add test button
        self.tts_test_button = QPushButton("Test Voice")
        self.tts_test_button.setToolTip("Test the TTS settings with custom or default text")
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

        # Add all controls to layout
        tts_layout.addRow("Enable Text-to-Speech:", self.tts_enabled_checkbox)
        tts_layout.addRow(self.tts_rate_label, self.tts_slow_checkbox)
        tts_layout.addRow(self.tts_volume_label, self.tts_volume_slider)
        tts_layout.addRow(self.tts_voice_label, self.tts_voice_combo)
        tts_layout.addRow(self.tts_test_text_label, self.tts_test_text_input)
        tts_layout.addRow("", self.tts_test_button)

        # Store TTS widgets for show/hide
        self.tts_config_widgets = [
            self.tts_rate_label, self.tts_slow_checkbox,
            self.tts_volume_label, self.tts_volume_slider,
            self.tts_voice_label, self.tts_voice_combo,
            self.tts_test_text_label, self.tts_test_text_input,
            self.tts_test_button
        ]

        # Connect checkbox to toggle visibility
        self.tts_enabled_checkbox.stateChanged.connect(self.toggle_tts_config_visibility)

        # Set initial visibility
        self.toggle_tts_config_visibility()
        
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
        url_layout.setLabelAlignment(Qt.AlignLeft)
        url_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        url_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        general_layout.setLabelAlignment(Qt.AlignLeft)
        general_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        general_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        # Load text-to-speech settings
        self.tts_enabled_checkbox.setChecked(self.settings.value("tts/enabled", False, type=bool))
        # TTS rate, volume, and voice settings will be loaded when UI controls are created
        
        # Load URL handler settings
        default_url_cmd = self.get_default_url_command()
        self.url_enabled_checkbox.setChecked(self.settings.value("url/enabled", False, type=bool))
        self.url_command_input.setText(self.settings.value("url/command_template", default_url_cmd))
        
        # Load app settings
        self.start_minimized_checkbox.setChecked(self.settings.value("app/start_minimized", False, type=bool))
        self.autostart_checkbox.setChecked(self.settings.value("app/autostart", False, type=bool))
        self.simulation_mode_checkbox.setChecked(self.settings.value("app/simulation_mode", True, type=bool))
    
    def get_default_url_command(self):
        """Get the default URL opening command for the current platform"""
        system = platform.system()
        if system == "Darwin":  # macOS
            return 'open "{url}"'
        elif system == "Windows":
            return 'start "" "{url}"'
        else:  # Linux or other
            return 'xdg-open "{url}"'

    def toggle_tts_config_visibility(self):
        """Show or hide TTS configuration controls based on enabled checkbox"""
        if hasattr(self, 'tts_config_widgets'):
            is_enabled = self.tts_enabled_checkbox.isChecked()
            for widget in self.tts_config_widgets:
                widget.setVisible(is_enabled)

    def save_settings(self):
        # Save text-to-speech settings
        self.settings.setValue("tts/enabled", self.tts_enabled_checkbox.isChecked())
        self.settings.setValue("tts/slow", self.tts_slow_checkbox.isChecked())
        self.settings.setValue("tts/volume", self.tts_volume_slider.value() / 100.0)
        self.settings.setValue("tts/voice_id", self.tts_voice_combo.currentData())
        
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

    def test_tts_command(self):
        """Test the text-to-speech functionality using pyttsx3"""
        try:
            # Get custom text if provided, otherwise use default
            custom_text = ""
            if hasattr(self, 'tts_test_text_input'):
                custom_text = self.tts_test_text_input.text().strip()
            test_message = custom_text if custom_text else "This is a test of the text to speech system"

            # Get current TTS settings from Config dialog widgets
            slow = self.tts_slow_checkbox.isChecked() if hasattr(self, 'tts_slow_checkbox') else False
            volume = (self.tts_volume_slider.value() / 100.0) if hasattr(self, 'tts_volume_slider') else 0.9
            voice_id = self.tts_voice_combo.currentData() if hasattr(self, 'tts_voice_combo') else None

            # Add to TTS queue for testing
            if hasattr(self, 'tts_manager') and self.tts_manager:
                self.tts_manager.add_to_queue(test_message, slow, volume, voice_id, "test")
                self.test_status_label.setText("TTS test added to queue...")
                self.test_status_label.setStyleSheet("color: green;")
            else:
                self.test_status_label.setText("TTS manager not available")
                self.test_status_label.setStyleSheet("color: red;")

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
                'Authorization': f'Bearer {token}',
                'User-Agent': USER_AGENT
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

# Help dialog class
class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Help & About")
        self.setModal(True)
        self.resize(500, 300)

        # Setup UI
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        layout.setContentsMargins(30, 30, 30, 30)

        # Get adaptive colors for styling
        colors = get_adaptive_colors()

        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Title label
        title_label = QLabel("Busylight Controller")
        title_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {colors['accent_blue']};
            margin-bottom: 10px;
        """)
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # Version label
        version_label = QLabel(f"Version {APP_VERSION}")
        version_label.setStyleSheet(f"""
            font-size: 16px;
            color: {colors['text_secondary']};
            margin-bottom: 20px;
        """)
        version_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(version_label)

        # Separator line
        separator = QLabel()
        separator.setFixedHeight(2)
        separator.setStyleSheet(f"background-color: {colors['border_secondary']};")
        layout.addWidget(separator)

        # Contact information
        contact_label = QLabel("For assistance contact:")
        contact_label.setStyleSheet(f"""
            font-size: 14px;
            font-weight: bold;
            color: {colors['text_primary']};
            margin-top: 10px;
        """)
        contact_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(contact_label)

        # Contact details
        contact_details = QLabel("Shane Harrell\n<shane.harrell@signalwire.com>")
        contact_details.setStyleSheet(f"""
            font-size: 14px;
            color: {colors['accent_blue']};
            margin-bottom: 20px;
        """)
        contact_details.setAlignment(Qt.AlignCenter)
        layout.addWidget(contact_details)

        # Add stretch to push button to bottom
        layout.addStretch()

        # Close button
        button_box = QDialogButtonBox(QDialogButtonBox.Ok)
        button_box.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_blue']};
                color: {colors['bg_primary']};
                border: none;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {colors['hover_bg']};
            }}
        """)
        button_box.accepted.connect(self.accept)
        layout.addWidget(button_box)

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
        form_layout.setLabelAlignment(Qt.AlignLeft)
        form_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form_layout.setSpacing(12)

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
        """Submit the status change to the API using centralized APIClient"""
        # Get parent window to access credentials
        parent_app = self.parent()
        if not parent_app or not hasattr(parent_app, 'username') or not hasattr(parent_app, 'password'):
            QMessageBox.warning(self, "API Error", "No authentication credentials available.")
            return

        # Create logger callback
        logger_callback = parent_app.add_log if hasattr(parent_app, 'add_log') else None

        # Create API client and submit
        client = APIClient(parent_app.username, parent_app.password, logger_callback)
        success, message = client.submit_status(
            status=data['action'],
            group=data['group'],
            source=parent_app.username,
            reason=data['reason']
        )

        # Show error if failed (success is logged by APIClient)
        if not success:
            QMessageBox.warning(self, "API Error", message)
    
    def get_result(self):
        """Return the result data"""
        return self.result_data

# Custom status update dialog class
class GroupStatusUpdateDialog(QDialog):
    """Simple dialog for updating a specific group's status"""
    def __init__(self, group_name, parent=None):
        super().__init__(parent)
        self.group_name = group_name
        self.setWindowTitle(f"Update Status - {group_name}")
        self.setModal(True)
        self.resize(500, 350)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Get parent app reference
        parent_app = self.parent()
        colors = get_adaptive_colors()

        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Title
        title_label = QLabel(f"Update Status for {self.group_name}")
        title_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {colors['accent_blue']};
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)

        # Form container
        form_group = QGroupBox()
        form_group.setStyleSheet(f"""
            QGroupBox {{
                border: 2px solid {colors['border_secondary']};
                border-radius: 8px;
                padding: 16px;
                background: {colors['bg_secondary']};
            }}
        """)
        form_layout = QVBoxLayout(form_group)
        form_layout.setSpacing(12)

        # Group field (read-only, pre-filled)
        group_label = QLabel("Group:")
        group_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold;")
        form_layout.addWidget(group_label)

        self.group_input = QLineEdit()
        self.group_input.setText(self.group_name)
        self.group_input.setReadOnly(True)
        self.group_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_secondary']};
                color: {colors['text_secondary']};
                min-height: 30px;
            }}
        """)
        form_layout.addWidget(self.group_input)

        # Source field (read-only, pre-filled with current user)
        source_label = QLabel("Source:")
        source_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold;")
        form_layout.addWidget(source_label)

        self.source_input = QLineEdit()
        if parent_app and hasattr(parent_app, 'username'):
            self.source_input.setText(parent_app.username)
        else:
            self.source_input.setText("Unknown User")
        self.source_input.setReadOnly(True)
        self.source_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_secondary']};
                color: {colors['text_secondary']};
                min-height: 30px;
            }}
        """)
        form_layout.addWidget(self.source_input)

        # Status dropdown
        status_label = QLabel("Status: *")
        status_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold;")
        form_layout.addWidget(status_label)

        self.status_combo = QComboBox()
        self.status_combo.addItems(['normal', 'warning', 'alert', 'alert-acked', 'error'])
        self.status_combo.setCurrentText('normal')
        self.status_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                min-height: 30px;
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.status_combo)

        # Reason field
        reason_label = QLabel("Reason:")
        reason_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold;")
        form_layout.addWidget(reason_label)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Optional: Reason for status update")
        self.reason_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                min-height: 30px;
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.reason_input)

        layout.addWidget(form_group)
        layout.addStretch()

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(12)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['bg_secondary']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border_secondary']};
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
            }}
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        submit_btn = QPushButton("Update Status")
        submit_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        submit_btn.clicked.connect(self.submit_status)
        button_layout.addWidget(submit_btn)

        layout.addLayout(button_layout)

    def submit_status(self):
        """Submit the status update to the API using centralized APIClient"""
        parent_app = self.parent()
        if not parent_app or not hasattr(parent_app, 'username') or not hasattr(parent_app, 'password'):
            QMessageBox.warning(self, "API Error", "No authentication credentials available.")
            return

        status = self.status_combo.currentText()
        reason = self.reason_input.text().strip()
        source = self.source_input.text()

        # Create logger callback
        logger_callback = parent_app.add_log if hasattr(parent_app, 'add_log') else None

        # Create API client and submit
        client = APIClient(parent_app.username, parent_app.password, logger_callback)
        success, message = client.submit_status(
            status=status,
            group=self.group_name,
            source=source,
            reason=reason if reason else None
        )

        # Handle result
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept()  # Close dialog
        else:
            QMessageBox.warning(self, "API Error", message)

class CustomStatusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Status Update")
        self.setModal(True)
        self.resize(500, 450)

        # Setup UI
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Get parent app reference for accessing Redis info and credentials
        parent_app = self.parent()

        # Get adaptive colors for styling
        colors = get_adaptive_colors()

        # Set dialog background
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
        """)

        # Title label
        title_label = QLabel("Set Status for any Group")
        title_label.setStyleSheet(f"""
            font-size: 16px;
            font-weight: bold;
            color: {colors['accent_blue']};
            margin-bottom: 10px;
        """)
        layout.addWidget(title_label)
        
        # Form container
        form_group = QGroupBox()
        form_group.setStyleSheet(f"""
            QGroupBox {{
                border: 2px solid {colors['border_secondary']};
                border-radius: 8px;
                padding: 16px;
                background: {colors['bg_secondary']};
            }}
        """)
        form_layout = QVBoxLayout(form_group)
        form_layout.setSpacing(12)

        # Status field (dropdown)
        status_label = QLabel("Status: *")
        status_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold;")
        form_layout.addWidget(status_label)

        self.status_combo = QComboBox()
        self.status_combo.addItems(['normal', 'warning', 'alert', 'alert-acked', 'error'])
        self.status_combo.setCurrentText('normal')
        self.status_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                min-height: 30px;
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.status_combo)

        # Group field (dropdown populated from Redis)
        group_label = QLabel("Group/Queue Name: *")
        group_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold; margin-top: 8px;")
        form_layout.addWidget(group_label)

        self.group_combo = QComboBox()
        self.group_combo.setEditable(False)  # Dropdown only, no custom input

        # Add placeholder as first item
        self.group_combo.addItem('-- Select a group --')

        # Populate with groups from Redis
        if parent_app and hasattr(parent_app, 'redis_info') and parent_app.redis_info:
            all_groups = parent_app.redis_info.get('all_groups', [])
            if all_groups:
                self.group_combo.addItems(sorted(all_groups))
            else:
                # Fallback to user's groups if all_groups not available
                user_groups = parent_app.redis_info.get('groups', ['default'])
                self.group_combo.addItems(sorted(user_groups))
        else:
            # Fallback default
            self.group_combo.addItem('default')

        self.group_combo.setCurrentIndex(0)  # Start with placeholder selected
        self.group_combo.setStyleSheet(f"""
            QComboBox {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                min-height: 30px;
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                selection-background-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.group_combo)

        # Source field
        source_label = QLabel("Source: *")
        source_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold; margin-top: 8px;")
        form_layout.addWidget(source_label)

        self.source_input = QLineEdit()
        # Set default to current username
        if parent_app and hasattr(parent_app, 'username'):
            self.source_input.setText(parent_app.username)
        else:
            self.source_input.setText("Unknown User")
        self.source_input.setReadOnly(True)  # Make source field immutable
        self.source_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_secondary']};
                color: {colors['text_secondary']};
                min-height: 30px;
            }}
        """)
        form_layout.addWidget(self.source_input)

        # Reason field (multi-line)
        reason_label = QLabel("Reason:")
        reason_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold; margin-top: 8px;")
        form_layout.addWidget(reason_label)

        self.reason_input = QTextEdit()
        self.reason_input.setPlaceholderText("Enter reason for status change (optional)")
        self.reason_input.setMaximumHeight(80)
        self.reason_input.setStyleSheet(f"""
            QTextEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
            }}
            QTextEdit:focus {{
                border-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.reason_input)

        # URL field
        url_label = QLabel("Pop-up URL:")
        url_label.setStyleSheet(f"color: {colors['text_primary']}; font-weight: bold; margin-top: 8px;")
        form_layout.addWidget(url_label)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://example.com/ticket/123 (optional)")
        self.url_input.setStyleSheet(f"""
            QLineEdit {{
                padding: 8px;
                border: 1px solid {colors['border_secondary']};
                border-radius: 4px;
                background: {colors['bg_primary']};
                color: {colors['text_primary']};
                min-height: 30px;
            }}
            QLineEdit:focus {{
                border-color: {colors['accent_blue']};
            }}
        """)
        form_layout.addWidget(self.url_input)

        layout.addWidget(form_group)

        # Required fields note
        required_note = QLabel("* Required fields")
        required_note.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px; font-style: italic;")
        layout.addWidget(required_note)

        # Buttons
        button_box = QDialogButtonBox()

        submit_button = QPushButton("Submit")
        submit_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_blue']};
                color: {colors['bg_primary']};
                border: none;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {colors['hover_bg']};
            }}
        """)
        submit_button.clicked.connect(self.submit_status)
        button_box.addButton(submit_button, QDialogButtonBox.AcceptRole)

        cancel_button = QPushButton("Cancel")
        cancel_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['bg_tertiary']};
                color: {colors['text_primary']};
                border: 1px solid {colors['border_secondary']};
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 14px;
                min-width: 100px;
            }}
            QPushButton:hover {{
                background-color: {colors['hover_bg']};
            }}
        """)
        cancel_button.clicked.connect(self.reject)
        button_box.addButton(cancel_button, QDialogButtonBox.RejectRole)

        layout.addWidget(button_box)

    def submit_status(self):
        """Validate and submit the status update"""
        # Get field values
        status = self.status_combo.currentText()
        group = self.group_combo.currentText().strip()
        source = self.source_input.text().strip()
        reason = self.reason_input.toPlainText().strip()
        url = self.url_input.text().strip()

        # Validate required fields
        if not group or group.startswith('--'):
            QMessageBox.warning(self, "Validation Error", "Please select a Group/Queue Name.")
            self.group_combo.setFocus()
            return

        if not source:
            QMessageBox.warning(self, "Validation Error", "Source is required.")
            self.source_input.setFocus()
            return

        # Call API
        self.submit_to_api(status, group, source, reason, url)

    def submit_to_api(self, status, group, source, reason, url):
        """Submit the status change to the API using centralized APIClient"""
        # Get parent window to access credentials
        parent_app = self.parent()
        if not parent_app or not hasattr(parent_app, 'username') or not hasattr(parent_app, 'password'):
            QMessageBox.warning(self, "API Error", "No authentication credentials available.")
            return

        # Create logger callback
        logger_callback = parent_app.add_log if hasattr(parent_app, 'add_log') else None

        # Create API client and submit
        client = APIClient(parent_app.username, parent_app.password, logger_callback)
        success, message = client.submit_status(
            status=status,
            group=group,
            source=source,
            reason=reason if reason else None,
            url=url if url else None
        )

        # Handle result
        if success:
            QMessageBox.information(self, "Success", message)
            self.accept()  # Close dialog
        else:
            QMessageBox.warning(self, "API Error", message)

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
        self.priority_timeline = []  # Store priority distribution over time
        self.category_timeline = []  # Store category distribution over time

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
        self.priority_chart.setMinimumSize(250, 300)
        self.priority_chart.setMaximumWidth(500)
        priority_layout.addWidget(self.priority_chart)
        charts_layout.addWidget(self.priority_group)

        # Category bar chart
        self.category_group = QGroupBox("Category Breakdown")
        category_layout = QVBoxLayout(self.category_group)
        self.category_chart = BarChartWidget()
        self.category_chart.setMinimumSize(250, 300)
        self.category_chart.setMaximumWidth(500)
        category_layout.addWidget(self.category_chart)
        charts_layout.addWidget(self.category_group)
        
        content_layout.addLayout(charts_layout)
        
        # Timeline chart for ticket counts over time
        self.timeline_group = QGroupBox("Ticket Count Timeline (24h)")
        timeline_layout = QVBoxLayout(self.timeline_group)
        self.timeline_chart = TimelineChartWidget()
        self.timeline_chart.setMinimumHeight(200)
        timeline_layout.addWidget(self.timeline_chart)
        content_layout.addWidget(self.timeline_group)

        # Priority distribution timeline (stacked area chart)
        self.priority_timeline_group = QGroupBox("Priority Distribution Timeline (24h)")
        priority_timeline_layout = QVBoxLayout(self.priority_timeline_group)
        self.priority_timeline_chart = StackedAreaChartWidget()
        self.priority_timeline_chart.setMinimumHeight(250)
        priority_timeline_layout.addWidget(self.priority_timeline_chart)
        content_layout.addWidget(self.priority_timeline_group)

        # Category trends timeline (multi-line chart)
        self.category_timeline_group = QGroupBox("Top 5 Category Trends (24h)")
        category_timeline_layout = QVBoxLayout(self.category_timeline_group)
        self.category_timeline_chart = MultiLineChartWidget()
        self.category_timeline_chart.setMinimumHeight(250)
        category_timeline_layout.addWidget(self.category_timeline_chart)
        content_layout.addWidget(self.category_timeline_group)

        # Ticket velocity chart (rate of change)
        self.velocity_group = QGroupBox("Ticket Velocity (Rate of Change)")
        velocity_layout = QVBoxLayout(self.velocity_group)
        self.velocity_chart = VelocityChartWidget()
        self.velocity_chart.setMinimumHeight(250)
        velocity_layout.addWidget(self.velocity_chart)
        content_layout.addWidget(self.velocity_group)

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

    def should_add_timeline_point(self, new_point, min_time_gap_seconds=300):
        """
        Determines if a new point should be added to timeline using smart change-based filtering.

        Args:
            new_point: dict with keys 'timestamp' (datetime) and 'count' (int)
            min_time_gap_seconds: minimum seconds between points if value unchanged (default 5 min)

        Returns:
            bool: True if point should be added, False otherwise
        """
        if not self.ticket_timeline:
            return True

        last_point = self.ticket_timeline[-1]
        time_diff = (new_point['timestamp'] - last_point['timestamp']).total_seconds()
        count_diff = abs(new_point['count'] - last_point['count'])

        # Add point if:
        # 1. Count changed (meaningful data)
        # 2. Significant time gap (prevents visual gaps in timeline)
        if count_diff > 0 or time_diff >= min_time_gap_seconds:
            return True

        return False

    def is_within_24_hours(self, timestamp):
        """Check if timestamp is within the last 24 hours"""
        import datetime
        now = datetime.datetime.now()
        time_diff = (now - timestamp).total_seconds()
        return time_diff <= (24 * 60 * 60)  # 24 hours in seconds

    def load_historical_timeline_data(self):
        """Load historical events from ticket_stats with smart filtering and 24-hour window"""
        try:
            # Get up to 100 events from Redis (enough to cover 24 hours of activity)
            historical_stats = self.redis_client.lrange("ticket_stats", 0, 99)

            if historical_stats:
                print(f"[{get_timestamp()}] Loading {len(historical_stats)} historical ticket stats for timeline")

                points_added = 0
                points_filtered = 0

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

                        # Skip if outside 24-hour window
                        if not self.is_within_24_hours(timestamp):
                            continue

                        # Create new point
                        new_point = {
                            'timestamp': timestamp,
                            'count': total_tickets
                        }

                        # Apply smart filtering - only add if meaningful change
                        if self.should_add_timeline_point(new_point, min_time_gap_seconds=300):
                            self.ticket_timeline.append(new_point)
                            points_added += 1

                            # Also add priority and category data for new charts
                            priorities = data.get('priorities', {})
                            categories = data.get('categories', {})

                            self.priority_timeline.append({
                                'timestamp': timestamp,
                                'priorities': priorities
                            })

                            self.category_timeline.append({
                                'timestamp': timestamp,
                                'categories': categories
                            })
                        else:
                            points_filtered += 1

                    except json.JSONDecodeError as e:
                        print(f"[{get_timestamp()}] Error parsing historical stats: {e}")
                        continue

                print(f"[{get_timestamp()}] Loaded {points_added} historical data points for timeline ({points_filtered} filtered as duplicates)")

                # Update all timeline charts with historical data
                self.timeline_chart.set_data(self.ticket_timeline)
                self.priority_timeline_chart.set_data(self.priority_timeline)
                self.category_timeline_chart.set_data(self.category_timeline)
                self.velocity_chart.set_data(self.ticket_timeline)

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
            
            # Add to timeline data with smart filtering
            import datetime
            timestamp = datetime.datetime.now()

            # Create new point
            new_point = {
                'timestamp': timestamp,
                'count': total_tickets
            }

            # Use unified filtering function (30 seconds for real-time updates)
            if self.should_add_timeline_point(new_point, min_time_gap_seconds=30):
                self.ticket_timeline.append(new_point)

                # Also add priority and category data for timeline charts
                priorities = data.get('priorities', {})
                categories = data.get('categories', {})

                self.priority_timeline.append({
                    'timestamp': timestamp,
                    'priorities': priorities
                })

                self.category_timeline.append({
                    'timestamp': timestamp,
                    'categories': categories
                })

                # Trim data points outside 24-hour window for all timelines
                cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=24)
                self.ticket_timeline = [
                    point for point in self.ticket_timeline
                    if point['timestamp'] > cutoff_time
                ]
                self.priority_timeline = [
                    point for point in self.priority_timeline
                    if point['timestamp'] > cutoff_time
                ]
                self.category_timeline = [
                    point for point in self.category_timeline
                    if point['timestamp'] > cutoff_time
                ]

                # Update all timeline charts
                self.timeline_chart.set_data(self.ticket_timeline)
                if hasattr(self, 'priority_timeline_chart'):
                    self.priority_timeline_chart.set_data(self.priority_timeline)
                if hasattr(self, 'category_timeline_chart'):
                    self.category_timeline_chart.set_data(self.category_timeline)
                if hasattr(self, 'velocity_chart'):
                    self.velocity_chart.set_data(self.ticket_timeline)

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
        
        # Chart area - legend at bottom now
        margin = 20
        legend_height = 80  # Space for legend at bottom
        # Make pie chart larger by using more of available space
        available_width = self.width() - margin * 2
        available_height = self.height() - margin * 2 - 40 - legend_height
        chart_size = min(available_width, available_height)
        # Center the chart horizontally
        chart_x = margin + max(0, (available_width - chart_size) // 2)
        chart_rect = QRect(chart_x, margin + 40, chart_size, chart_size)
        
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
        
        # Draw pie slices
        start_angle = 0
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
            start_angle += span_angle

        # Draw legend at bottom horizontally
        legend_y = chart_rect.bottom() + 20
        legend_font = QFont()
        legend_font.setPointSize(9)
        painter.setFont(legend_font)

        # Calculate how many items per row based on available width
        items_per_row = min(4, len(sorted_data))
        item_width = self.width() // items_per_row

        for i, (label, value) in enumerate(sorted_data):
            row = i // items_per_row
            col = i % items_per_row

            legend_x = col * item_width + 10
            current_y = legend_y + row * 25

            # Draw color box
            base_color = QColor(self.colors[i % len(self.colors)])
            color_rect = QRect(legend_x, current_y + 2, 16, 16)
            painter.setBrush(base_color)
            painter.setPen(QColor(colors['border_secondary']))
            painter.drawRect(color_rect)

            # Draw label text
            painter.setPen(QColor(colors['text_primary']))
            percentage = (value / total) * 100
            display_label = label if len(label) <= 8 else label[:6] + "..."
            legend_text = f"{display_label}: {value} ({percentage:.1f}%)"
            text_rect = QRect(legend_x + 22, current_y, item_width - 32, 20)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, legend_text)

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
        
        # Chart area with space for legend at bottom
        margin = 30
        legend_height = 80  # Space for legend at bottom
        chart_rect = self.rect().adjusted(margin, margin + 40, -margin, -margin - legend_height)
        
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

        # Draw legend at bottom horizontally
        legend_y = chart_rect.bottom() + 10
        legend_font = QFont()
        legend_font.setPointSize(9)
        painter.setFont(legend_font)

        # Calculate how many items per row based on available width
        items_per_row = min(5, len(sorted_data))
        item_width = self.width() // items_per_row

        for i, (label, value) in enumerate(sorted_data):
            row = i // items_per_row
            col = i % items_per_row

            legend_x = col * item_width + 10
            current_y = legend_y + row * 25

            # Draw color box
            color = QColor(self.colors[i % len(self.colors)])
            color_rect = QRect(legend_x, current_y + 2, 16, 16)
            painter.setBrush(color)
            painter.setPen(QColor(colors['border_secondary']))
            painter.drawRect(color_rect)

            # Draw label text
            painter.setPen(QColor(colors['text_primary']))
            display_label = label if len(label) <= 12 else label[:10] + "..."
            text_rect = QRect(legend_x + 22, current_y, item_width - 32, 20)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, display_label)

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
        mouse_pos = event.position().toPoint()
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
        
        # Draw hovered point highlight only (no dots for all points)
        if self.hover_point is not None:
            point, data = self.data_points[self.hover_point]
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

class StackedAreaChartWidget(QWidget):
    """Stacked area chart showing priority distribution over time"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data = []  # List of {'timestamp': datetime, 'priorities': {'P1': X, 'P2': Y, ...}}
        self.setMinimumHeight(250)

    def set_data(self, timeline_data):
        """Set the timeline data with priority information"""
        self.timeline_data = timeline_data
        self.update()

    def paintEvent(self, event):
        """Paint the stacked area chart"""
        if not self.timeline_data or len(self.timeline_data) < 1:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = get_adaptive_colors()

        # Priority colors
        priority_colors = {
            'P1': '#ef5350',  # Red
            'P2': '#ff9800',  # Orange
            'P3': '#4a9eff',  # Blue
            'P4': '#4caf50'   # Green
        }

        # Chart area
        margin = 50
        chart_rect = self.rect().adjusted(margin, margin + 30, -margin, -margin - 40)

        # Draw title
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, "Priority Distribution Over Time")

        if len(self.timeline_data) == 1:
            # Single point - just show text
            painter.setPen(QColor(colors['text_secondary']))
            painter.drawText(chart_rect, Qt.AlignCenter, "Need more data points for timeline")
            return

        # Find max total for scaling
        max_total = 0
        for data_point in self.timeline_data:
            priorities = data_point.get('priorities', {})
            total = sum(priorities.values())
            max_total = max(max_total, total)

        if max_total == 0:
            max_total = 1

        # Draw grid
        painter.setPen(QColor(colors['border_secondary']))
        for i in range(5):
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            painter.drawLine(chart_rect.left(), int(y_pos), chart_rect.right(), int(y_pos))

        # Draw axes
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight())
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())

        # Draw stacked areas (from bottom to top: P4, P3, P2, P1)
        priority_order = ['P4', 'P3', 'P2', 'P1']

        for priority in priority_order:
            polygon_points = []

            # Bottom edge (left to right)
            for i, data_point in enumerate(self.timeline_data):
                priorities = data_point.get('priorities', {})

                # Calculate cumulative height up to but not including this priority
                cumulative = 0
                for p in reversed(priority_order):
                    if p == priority:
                        break
                    cumulative += priorities.get(p, 0)

                x = chart_rect.left() + (i / (len(self.timeline_data) - 1)) * chart_rect.width()
                y = chart_rect.bottom() - (cumulative / max_total) * chart_rect.height()
                polygon_points.append(QPoint(int(x), int(y)))

            # Top edge (right to left)
            for i in reversed(range(len(self.timeline_data))):
                data_point = self.timeline_data[i]
                priorities = data_point.get('priorities', {})

                # Calculate cumulative height including this priority
                cumulative = 0
                for p in reversed(priority_order):
                    cumulative += priorities.get(p, 0)
                    if p == priority:
                        break

                x = chart_rect.left() + (i / (len(self.timeline_data) - 1)) * chart_rect.width()
                y = chart_rect.bottom() - (cumulative / max_total) * chart_rect.height()
                polygon_points.append(QPoint(int(x), int(y)))

            # Draw the filled area
            if polygon_points:
                polygon = QPolygon(polygon_points)
                color = QColor(priority_colors[priority])
                color.setAlpha(180)  # Semi-transparent
                painter.setBrush(QBrush(color))
                painter.setPen(Qt.NoPen)
                painter.drawPolygon(polygon)

        # Draw Y-axis labels
        painter.setPen(QColor(colors['text_secondary']))
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)

        for i in range(5):
            y_val = (max_total / 4) * i
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            label_rect = QRect(5, int(y_pos) - 10, margin - 10, 20)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{int(y_val)}")

        # Draw X-axis time labels
        num_labels = min(5, len(self.timeline_data))
        for i in range(num_labels):
            data_index = int(i * (len(self.timeline_data) - 1) / (num_labels - 1))
            time_str = self.timeline_data[data_index]['timestamp'].strftime("%H:%M")
            x_pos = chart_rect.left() + (data_index / (len(self.timeline_data) - 1)) * chart_rect.width()
            time_rect = QRect(int(x_pos) - 20, chart_rect.bottom() + 5, 40, 20)
            painter.drawText(time_rect, Qt.AlignCenter, time_str)

        # Draw legend at bottom
        legend_y = chart_rect.bottom() + 30
        legend_x = chart_rect.left()
        box_size = 12

        for i, priority in enumerate(priority_order):
            x_offset = i * 80
            # Draw color box
            color = QColor(priority_colors[priority])
            painter.setBrush(QBrush(color))
            painter.setPen(Qt.NoPen)
            painter.drawRect(legend_x + x_offset, legend_y, box_size, box_size)

            # Draw label
            painter.setPen(QColor(colors['text_primary']))
            painter.setFont(label_font)
            label_rect = QRect(legend_x + x_offset + box_size + 5, legend_y - 2, 60, 16)
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, priority)

class MultiLineChartWidget(QWidget):
    """Multi-line chart showing top categories trending over time"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data = []  # List of {'timestamp': datetime, 'categories': {'VOICE': X, 'MESSAGING': Y, ...}}
        self.setMinimumHeight(250)
        self.hover_point = None
        self.setMouseTracking(True)

    def set_data(self, timeline_data):
        """Set the timeline data with category information"""
        self.timeline_data = timeline_data
        self.update()

    def paintEvent(self, event):
        """Paint the multi-line chart"""
        if not self.timeline_data or len(self.timeline_data) < 1:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = get_adaptive_colors()

        # Category colors (Material Design palette)
        category_colors = [
            '#ef5350',  # Red
            '#ff9800',  # Orange
            '#4a9eff',  # Blue
            '#4caf50',  # Green
            '#ab47bc'   # Purple
        ]

        # Chart area
        margin = 50
        chart_rect = self.rect().adjusted(margin, margin + 30, -margin, -margin - 40)

        # Draw title
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, "Top 5 Category Trends")

        if len(self.timeline_data) == 1:
            painter.setPen(QColor(colors['text_secondary']))
            painter.drawText(chart_rect, Qt.AlignCenter, "Need more data points for timeline")
            return

        # Find top 5 categories by total volume
        category_totals = {}
        for data_point in self.timeline_data:
            categories = data_point.get('categories', {})
            for cat, count in categories.items():
                category_totals[cat] = category_totals.get(cat, 0) + count

        top_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        top_category_names = [cat for cat, _ in top_categories]

        if not top_category_names:
            painter.setPen(QColor(colors['text_secondary']))
            painter.drawText(chart_rect, Qt.AlignCenter, "No category data available")
            return

        # Find max value for scaling
        max_value = 0
        for data_point in self.timeline_data:
            categories = data_point.get('categories', {})
            for cat in top_category_names:
                max_value = max(max_value, categories.get(cat, 0))

        if max_value == 0:
            max_value = 1

        # Draw grid
        painter.setPen(QColor(colors['border_secondary']))
        for i in range(5):
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            painter.drawLine(chart_rect.left(), int(y_pos), chart_rect.right(), int(y_pos))

        # Draw axes
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.bottomRight())
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())

        # Draw lines for each category
        for cat_idx, category in enumerate(top_category_names):
            points = []
            color = category_colors[cat_idx % len(category_colors)]

            for i, data_point in enumerate(self.timeline_data):
                categories = data_point.get('categories', {})
                count = categories.get(category, 0)

                x = chart_rect.left() + (i / (len(self.timeline_data) - 1)) * chart_rect.width()
                y = chart_rect.bottom() - (count / max_value) * chart_rect.height()
                points.append(QPoint(int(x), int(y)))

            # Draw line
            painter.setPen(QPen(QColor(color), 2))
            for i in range(len(points) - 1):
                painter.drawLine(points[i], points[i + 1])

        # Draw Y-axis labels
        painter.setPen(QColor(colors['text_secondary']))
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)

        for i in range(5):
            y_val = (max_value / 4) * i
            y_pos = chart_rect.bottom() - (i / 4) * chart_rect.height()
            label_rect = QRect(5, int(y_pos) - 10, margin - 10, 20)
            painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"{int(y_val)}")

        # Draw X-axis time labels
        num_labels = min(5, len(self.timeline_data))
        for i in range(num_labels):
            data_index = int(i * (len(self.timeline_data) - 1) / (num_labels - 1))
            time_str = self.timeline_data[data_index]['timestamp'].strftime("%H:%M")
            x_pos = chart_rect.left() + (data_index / (len(self.timeline_data) - 1)) * chart_rect.width()
            time_rect = QRect(int(x_pos) - 20, chart_rect.bottom() + 5, 40, 20)
            painter.drawText(time_rect, Qt.AlignCenter, time_str)

        # Draw legend
        legend_y = chart_rect.bottom() + 30
        legend_x = chart_rect.left()
        box_size = 12

        for i, category in enumerate(top_category_names):
            x_offset = i * 100
            if x_offset + 100 > chart_rect.width():
                break  # Don't overflow

            color = category_colors[i % len(category_colors)]
            painter.setBrush(QBrush(QColor(color)))
            painter.setPen(Qt.NoPen)
            painter.drawRect(legend_x + x_offset, legend_y, box_size, box_size)

            painter.setPen(QColor(colors['text_primary']))
            painter.setFont(label_font)
            label_rect = QRect(legend_x + x_offset + box_size + 5, legend_y - 2, 85, 16)
            painter.drawText(label_rect, Qt.AlignLeft | Qt.AlignVCenter, category[:12])  # Truncate long names

class VelocityChartWidget(QWidget):
    """Bar chart showing ticket velocity (rate of change)"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeline_data = []  # List of {'timestamp': datetime, 'count': int, 'delta': int}
        self.setMinimumHeight(250)

    def set_data(self, timeline_data):
        """Set the timeline data with velocity information"""
        self.timeline_data = timeline_data
        self.update()

    def paintEvent(self, event):
        """Paint the velocity chart"""
        if not self.timeline_data or len(self.timeline_data) < 2:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        colors = get_adaptive_colors()

        # Chart area
        margin = 50
        chart_rect = self.rect().adjusted(margin, margin + 30, -margin, -margin - 20)

        # Draw title
        painter.setPen(QColor(colors['text_primary']))
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        painter.setFont(title_font)
        title_rect = QRect(0, 5, self.width(), 30)
        painter.drawText(title_rect, Qt.AlignCenter, "Ticket Velocity (Rate of Change)")

        # Calculate deltas
        deltas = []
        for i in range(1, len(self.timeline_data)):
            delta = self.timeline_data[i]['count'] - self.timeline_data[i-1]['count']
            deltas.append({'timestamp': self.timeline_data[i]['timestamp'], 'delta': delta})

        if not deltas:
            return

        # Find max absolute delta for scaling
        max_delta = max(abs(d['delta']) for d in deltas)
        if max_delta == 0:
            max_delta = 1

        # Draw center line (zero line)
        center_y = chart_rect.top() + chart_rect.height() // 2
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.left(), center_y, chart_rect.right(), center_y)

        # Draw grid lines
        painter.setPen(QColor(colors['border_secondary']))
        for i in range(3):  # Draw lines at +max, 0, -max
            if i == 1:
                continue  # Skip center (already drawn)
            y_pos = chart_rect.top() + (i / 2) * chart_rect.height()
            painter.drawLine(chart_rect.left(), int(y_pos), chart_rect.right(), int(y_pos))

        # Draw axes
        painter.setPen(QColor(colors['text_primary']))
        painter.drawLine(chart_rect.bottomLeft(), chart_rect.topLeft())

        # Calculate bar width
        bar_width = max(2, int(chart_rect.width() / len(deltas) * 0.8))

        # Draw bars
        for i, data in enumerate(deltas):
            delta = data['delta']

            x = chart_rect.left() + (i / max(1, len(deltas) - 1)) * chart_rect.width()

            if delta > 0:
                # Positive change (green bar above center)
                height = (delta / max_delta) * (chart_rect.height() / 2)
                bar_rect = QRect(int(x) - bar_width // 2, int(center_y - height), bar_width, int(height))
                painter.fillRect(bar_rect, QColor(colors['accent_green']))
            elif delta < 0:
                # Negative change (red bar below center)
                height = abs(delta / max_delta) * (chart_rect.height() / 2)
                bar_rect = QRect(int(x) - bar_width // 2, center_y, bar_width, int(height))
                painter.fillRect(bar_rect, QColor(colors['accent_red']))

        # Draw Y-axis labels
        painter.setPen(QColor(colors['text_secondary']))
        label_font = QFont()
        label_font.setPointSize(9)
        painter.setFont(label_font)

        # Positive label
        label_rect = QRect(5, chart_rect.top(), margin - 10, 20)
        painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"+{int(max_delta)}")

        # Zero label
        label_rect = QRect(5, center_y - 10, margin - 10, 20)
        painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, "0")

        # Negative label
        label_rect = QRect(5, chart_rect.bottom() - 20, margin - 10, 20)
        painter.drawText(label_rect, Qt.AlignRight | Qt.AlignVCenter, f"-{int(max_delta)}")

        # Draw X-axis time labels (show fewer for velocity)
        num_labels = min(3, len(deltas))
        for i in range(num_labels):
            data_index = int(i * (len(deltas) - 1) / max(1, num_labels - 1))
            time_str = deltas[data_index]['timestamp'].strftime("%H:%M")
            x_pos = chart_rect.left() + (data_index / max(1, len(deltas) - 1)) * chart_rect.width()
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

# Worker class for non-blocking text-to-speech
class TTSManager(QThread):
    """Queue-based TTS manager with single pyttsx3 engine"""
    tts_completed = pyqtSignal(str)  # Emits message type when complete
    tts_error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.queue = []
        self.is_running = True
        self.engine = None
        self.current_settings = {}
        self.max_queue_size = 5  # Limit queue to prevent buildup

    def add_to_queue(self, text, slow=False, volume=0.9, voice_id=None, message_type="unknown"):
        """Add a TTS request to the queue"""
        # If queue is at max size, remove oldest items
        if len(self.queue) >= self.max_queue_size:
            removed = self.queue.pop(0)
            print(f"[{get_timestamp()}] TTS queue full, dropping oldest message: '{removed['text'][:30]}...'")

        self.queue.append({
            'text': text,
            'slow': slow,
            'volume': volume,
            'voice_id': voice_id,
            'message_type': message_type
        })
        speed_str = "slow" if slow else "normal"
        print(f"[{get_timestamp()}] TTS request queued: '{text[:50]}...' (speed: {speed_str}, queue size: {len(self.queue)})")

    def stop(self):
        """Stop the TTS manager"""
        self.is_running = False
        if self.engine:
            try:
                self.engine.stop()
            except:
                pass

    def run(self):
        """Process TTS queue continuously"""
        print(f"[{get_timestamp()}] TTSManager: Starting queue processor with gTTS")

        # Initialize pygame mixer once
        try:
            pygame.mixer.init()
            print(f"[{get_timestamp()}] TTSManager: Pygame mixer initialized")
        except Exception as e:
            print(f"[{get_timestamp()}] TTSManager: Failed to initialize pygame mixer: {e}")
            return

        while self.is_running:
            if self.queue:
                # Get next request from queue
                request = self.queue.pop(0)
                text = request['text']
                slow = request['slow']
                volume = request['volume']
                voice_id = request['voice_id']
                message_type = request['message_type']

                speed_str = "slow" if slow else "normal"
                print(f"[{get_timestamp()}] TTSManager: Processing '{text[:50]}...' (speed: {speed_str}, volume: {volume})")

                try:
                    # Map voice_id to gTTS TLD for different accents
                    tld_map = {
                        'en-us': 'com',      # US English
                        'en-uk': 'co.uk',    # UK English
                        'en-au': 'com.au',   # Australian English
                        'en-in': 'co.in',    # Indian English
                        'en-ca': 'ca',       # Canadian English
                        'en-za': 'co.za',    # South African English
                        'en-ie': 'ie',       # Irish English
                        'en-ng': 'com.ng',   # Nigerian English
                    }
                    tld = tld_map.get(voice_id, 'com')  # Default to US English

                    # Generate speech using gTTS with timeout
                    print(f"[{get_timestamp()}] TTSManager: Generating speech with gTTS (accent: {voice_id or 'en-us'}, slow: {slow})")
                    tts = gTTS(text=text, lang='en', tld=tld, slow=slow, timeout=3)

                    # Write to BytesIO instead of temp file (more efficient)
                    # This makes the actual API call to Google
                    audio_fp = BytesIO()
                    tts.write_to_fp(audio_fp)
                    audio_fp.seek(0)
                    print(f"[{get_timestamp()}] TTSManager: Audio generated in memory")

                    # Play audio using pygame
                    print(f"[{get_timestamp()}] TTSManager: Playing audio")
                    pygame.mixer.music.load(audio_fp)
                    pygame.mixer.music.set_volume(volume)
                    pygame.mixer.music.play()

                    # Wait for playback to finish
                    while pygame.mixer.music.get_busy():
                        self.msleep(100)

                    print(f"[{get_timestamp()}] TTSManager: Playback completed")

                    # Emit completion signal
                    self.tts_completed.emit(message_type)

                except Exception as e:
                    # Check if it's a timeout error
                    error_type = type(e).__name__
                    if 'timeout' in str(e).lower() or error_type in ['Timeout', 'ConnectTimeout', 'ReadTimeout']:
                        error_msg = f"TTS timeout after 3 seconds - Google TTS API not responding"
                        print(f"[{get_timestamp()}] TTSManager: {error_msg}")
                    else:
                        error_msg = f"TTS error ({error_type}): {e}"
                        print(f"[{get_timestamp()}] TTSManager: {error_msg}")

                    self.tts_error.emit(error_msg)

                finally:
                    # Small delay between messages
                    self.msleep(200)

            else:
                # Sleep briefly when queue is empty
                self.msleep(100)

        # Clean up pygame mixer
        try:
            pygame.mixer.quit()
        except:
            pass

        print(f"[{get_timestamp()}] TTSManager: Queue processor stopped")

# Worker class to handle redis operations in background
class RedisWorker(QObject):
    status_updated = pyqtSignal(str)
    connection_status = pyqtSignal(str)
    log_message = pyqtSignal(str)
    ticket_received = pyqtSignal(dict)  # New signal for ticket information
    group_status_updated = pyqtSignal(str, str, dict)  # group, status, full_data
    user_status_updated = pyqtSignal(str, str, dict)  # username, status, full_data (display only)
    users_list_received = pyqtSignal(list)  # list of user dicts from API

    def __init__(self, redis_info, username=None, parent=None):
        super().__init__(parent)
        self.redis_client = None
        self.is_running = True
        self.pubsub = None
        self.username = username

        # Health check and reconnection settings
        self.last_ping_time = 0
        self.ping_interval = 30  # Ping every 30 seconds
        self.reconnect_delay = 5  # Start with 5 seconds
        self.max_reconnect_delay = 60  # Max 60 seconds between reconnects
        self.connected = False

        # Track processed events to prevent duplicates on reconnection
        # Store hashes of recent events (keep last 100)
        self.processed_events = set()
        self.max_processed_events = 100

        # Status priority mapping (highest to lowest priority)
        # Error -> Alert -> Alert-Acked -> Warning -> Normal
        self.status_priority = {
            'error': 5,      # Most critical
            'alert': 4,
            'alert-acked': 3,
            'warning': 2,
            'normal': 0,
            'default': 0,
            'off': 0
        }

        # Track current status for each group in user_groups
        self.group_statuses = {}
        self.current_overall_status = 'normal'

        # Track all users for user presence status (display only)
        self.all_users = []  # List of all usernames to subscribe to

        # Use Redis info from login response
        if redis_info:
            self.redis_host = redis_info['host']  # Use host as-is from API
            self.redis_port = redis_info['port']
            self.redis_password = redis_info['password']  # Could be None
            # Track both user's groups (for overall status) and all groups (for monitoring)
            self.user_groups = list(redis_info['groups'])  # Groups user is a member of
            self.groups = redis_info.get('all_groups', redis_info['groups'])  # All groups to subscribe to

            # Add username to user_groups so personal status affects overall status
            if self.username and self.username not in self.user_groups:
                self.user_groups.append(self.username)
        else:
            # Fallback to default values if no redis_info provided
            self.redis_host = "localhost"
            self.redis_port = 6379
            self.redis_password = None
            self.user_groups = ["default"]
            self.groups = ["default"]
            
    def get_highest_priority_status(self):
        """Calculate the highest priority status across all user groups"""
        if not self.group_statuses:
            return 'normal'

        # Find the status with the highest priority value
        highest_priority = -1
        highest_status = 'normal'

        for group in self.user_groups:
            if group in self.group_statuses:
                status = self.group_statuses[group]
                priority = self.status_priority.get(status, 0)
                if priority > highest_priority:
                    highest_priority = priority
                    highest_status = status

        return highest_status

    def update_group_status(self, group, status):
        """Update a group's status and emit overall status if priority changed"""
        # Update the group's status
        self.group_statuses[group] = status

        # Only recalculate overall status for user's groups
        if group in self.user_groups:
            # Calculate the new highest priority status
            new_overall_status = self.get_highest_priority_status()

            # Only emit if the overall status changed
            if new_overall_status != self.current_overall_status:
                self.log_message.emit(f"[{get_timestamp()}] Overall status changed from '{self.current_overall_status}' to '{new_overall_status}' (triggered by group '{group}')")
                self.current_overall_status = new_overall_status
                self.status_updated.emit(new_overall_status)
            else:
                self.log_message.emit(f"[{get_timestamp()}] Group '{group}' status updated to '{status}', but overall status remains '{self.current_overall_status}'")
        else:
            # Just log for monitoring groups
            self.log_message.emit(f"[{get_timestamp()}] Group '{group}' status '{status}' - monitoring only, not affecting overall status")

    def get_event_hash(self, data):
        """Generate a hash for an event to detect duplicates"""
        # Create a unique identifier from key fields
        key_fields = {
            'group': data.get('group', ''),
            'status': data.get('status', ''),
            'timestamp': data.get('timestamp', ''),
            'ticket': data.get('ticket', ''),
            'summary': data.get('summary', ''),
        }
        # Create a deterministic string from the fields
        event_str = json.dumps(key_fields, sort_keys=True)
        return hashlib.md5(event_str.encode()).hexdigest()

    def is_event_processed(self, event_hash):
        """Check if we've already processed this event"""
        return event_hash in self.processed_events

    def mark_event_processed(self, event_hash):
        """Mark an event as processed and manage cache size"""
        self.processed_events.add(event_hash)
        # Keep only the most recent events to prevent unbounded growth
        if len(self.processed_events) > self.max_processed_events:
            # Remove oldest entries (convert to list, remove first half, convert back)
            events_list = list(self.processed_events)
            self.processed_events = set(events_list[-self.max_processed_events:])

    def check_connection_health(self):
        """Perform a health check on the Redis connection"""
        try:
            current_time = time.time()
            # Only ping if enough time has passed since last ping
            if current_time - self.last_ping_time >= self.ping_interval:
                self.redis_client.ping()
                self.last_ping_time = current_time
                return True
            return True
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Health check failed: {e}")
            return False

    def connect_to_redis(self):
        try:
            # Close existing connection if present (for reconnection scenarios)
            if self.redis_client:
                try:
                    self.redis_client.close()
                except:
                    pass
            if self.pubsub:
                try:
                    self.pubsub.close()
                except:
                    pass

            # Log connection attempt details
            self.log_message.emit(f"[{get_timestamp()}] Attempting Redis connection to {self.redis_host}:{self.redis_port}")
            if self.redis_password:
                self.log_message.emit(f"[{get_timestamp()}] Using password authentication (password length: {len(self.redis_password)})")
            else:
                self.log_message.emit(f"[{get_timestamp()}] No password authentication")

            # Connect directly with provided credentials and socket keepalive enabled
            keepalive_options = {}
            # Use proper socket constants - hasattr checks handle platform differences
            if hasattr(socket, 'TCP_KEEPIDLE'):
                keepalive_options[socket.TCP_KEEPIDLE] = 60   # seconds before sending keepalive probes
            if hasattr(socket, 'TCP_KEEPINTVL'):
                keepalive_options[socket.TCP_KEEPINTVL] = 10  # interval between keepalive probes
            if hasattr(socket, 'TCP_KEEPCNT'):
                keepalive_options[socket.TCP_KEEPCNT] = 3     # number of failed probes before closing

            self.redis_client = redis.StrictRedis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,  # Will be None if no auth required
                db=0,
                decode_responses=True,
                socket_timeout=10,
                socket_connect_timeout=10,
                socket_keepalive=True,
                socket_keepalive_options=keepalive_options,
                health_check_interval=30  # Automatically ping every 30 seconds
            )

            # Check if Redis connection is successful
            self.redis_client.ping()
            self.log_message.emit(f"[{get_timestamp()}] Connected to Redis at {self.redis_host}:{self.redis_port}")
            self.connection_status.emit("connected")
            self.connected = True
            self.last_ping_time = time.time()
            # Reset reconnect delay on successful connection
            self.reconnect_delay = 5
            return True
        except Exception as e:
            self.log_message.emit(f"[{get_timestamp()}] Redis connection error: {e}")
            self.log_message.emit(f"[{get_timestamp()}] Connection details - Host: {self.redis_host}, Port: {self.redis_port}, Password: {'Yes' if self.redis_password else 'No'}")
            self.connection_status.emit("disconnected")
            self.connected = False
            return False
            
    def run(self):
        # Main loop with automatic reconnection
        while self.is_running:
            # Try to connect or reconnect
            if not self.connect_to_redis():
                # Connection failed, wait before retrying
                self.log_message.emit(f"[{get_timestamp()}] Will retry connection in {self.reconnect_delay} seconds...")
                for _ in range(self.reconnect_delay * 10):  # Check every 100ms
                    if not self.is_running:
                        return
                    QThread.msleep(100)

                # Increase reconnect delay with exponential backoff
                self.reconnect_delay = min(self.reconnect_delay * 2, self.max_reconnect_delay)
                continue

            # Connection successful, proceed with getting initial status
            try:
                self.load_initial_status()
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error getting initial status: {e}")
                self.connected = False
                continue

            # Subscribe to all group status channels
            try:
                self.pubsub = self.redis_client.pubsub()
                for group in self.groups:
                    channel_name = f"status:{group}"
                    self.pubsub.subscribe(channel_name)
                    self.log_message.emit(f"[{get_timestamp()}] Subscribed to {channel_name}")

                # Subscribe to username-specific channel if username is provided
                if self.username:
                    username_channel = f"status:{self.username}"
                    self.pubsub.subscribe(username_channel)
                    self.log_message.emit(f"[{get_timestamp()}] Subscribed to {username_channel}")

                # Subscribe to user presence status channels for all users
                user_status_count = 0
                for user in self.all_users:
                    user_status_channel = f"user_status:{user}"
                    self.pubsub.subscribe(user_status_channel)
                    user_status_count += 1
                if user_status_count > 0:
                    self.log_message.emit(f"[{get_timestamp()}] Subscribed to {user_status_count} user status channels")

                channel_count = len(self.groups) + (1 if self.username else 0) + user_status_count
                self.log_message.emit(f"[{get_timestamp()}] Listening for messages on {channel_count} status channels...")
            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error subscribing to channels: {e}")
                self.connected = False
                continue

            # Listen for messages in a loop with health checks
            consecutive_errors = 0
            max_consecutive_errors = 3

            while self.is_running and self.connected:
                try:
                    # Perform periodic health check
                    if not self.check_connection_health():
                        self.log_message.emit(f"[{get_timestamp()}] Connection health check failed, reconnecting...")
                        self.connected = False
                        self.connection_status.emit("disconnected")
                        break

                    # Get message from pubsub
                    message = self.pubsub.get_message(timeout=0.1)
                    if message and message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            channel = message["channel"]

                            # Check if this is a user presence status channel (display only, no light control)
                            if channel.startswith('user_status:'):
                                username = channel.replace('user_status:', '')
                                status = data.get('status', USER_STATUS_OFFLINE)
                                self.log_message.emit(f"[{get_timestamp()}] User status from {channel}: {status}")
                                # Emit user status signal (display only, no light control)
                                self.user_status_updated.emit(username, status, data)
                                consecutive_errors = 0
                                continue

                            # Handle group alert status channels (controls busylight)
                            # Extract group name from channel (remove 'status:' prefix)
                            group = channel.replace('status:', '') if channel.startswith('status:') else channel

                            # Add group to data if not present
                            if 'group' not in data:
                                data['group'] = group

                            # Check if this event has already been processed
                            event_hash = self.get_event_hash(data)
                            if self.is_event_processed(event_hash):
                                self.log_message.emit(f"[{get_timestamp()}] Skipping duplicate event from {channel}")
                            else:
                                self.log_message.emit(f"[{get_timestamp()}] Received from {channel}: {data}")
                                status = data.get('status', 'error')

                                # Mark event as processed
                                self.mark_event_processed(event_hash)

                                # Emit group-specific status
                                self.group_status_updated.emit(group, status, data)

                                # Update group status and recalculate overall status based on priority
                                self.update_group_status(group, status)

                                # Process ticket information if available
                                self.process_ticket_info(data, group)

                            # Reset error counter on successful message processing
                            consecutive_errors = 0

                        except json.JSONDecodeError as e:
                            self.log_message.emit(f"[{get_timestamp()}] Error decoding message: {e}")
                        except Exception as e:
                            self.log_message.emit(f"[{get_timestamp()}] Error processing message: {e}")
                            consecutive_errors += 1

                except redis.ConnectionError as e:
                    self.log_message.emit(f"[{get_timestamp()}] Redis connection lost: {e}")
                    self.connected = False
                    self.connection_status.emit("disconnected")
                    break
                except Exception as e:
                    self.log_message.emit(f"[{get_timestamp()}] Error in message loop: {e}")
                    consecutive_errors += 1

                # Check if we've had too many consecutive errors
                if consecutive_errors >= max_consecutive_errors:
                    self.log_message.emit(f"[{get_timestamp()}] Too many consecutive errors, reconnecting...")
                    self.connected = False
                    self.connection_status.emit("disconnected")
                    break

                # Small sleep to prevent CPU hogging
                QThread.msleep(100)

            # If we exited the loop but should still be running, we'll reconnect
            if self.is_running and not self.connected:
                self.log_message.emit(f"[{get_timestamp()}] Connection lost, will attempt to reconnect...")

    def load_initial_status(self):
        """Load the most recent status from group-specific status keys"""
        group_found_status = {}

        # Build list of all channels to load status from (groups + username channel)
        channels_to_load = list(self.groups)
        if self.username:
            channels_to_load.append(self.username)

        # Get the most recent status for each group from their individual status keys
        for group in channels_to_load:
            status_key = f"status:{group}"
            try:
                # Get the most recent status event for this group
                recent_event = self.redis_client.lindex(status_key, 0)  # Most recent is at index 0
                if recent_event:
                    try:
                        data = json.loads(recent_event)
                        event_status = data.get('status')

                        # Add group to data if not present
                        if 'group' not in data:
                            data['group'] = group

                        if event_status:
                            # Check if we've already processed this event
                            event_hash = self.get_event_hash(data)
                            if not self.is_event_processed(event_hash):
                                group_found_status[group] = {
                                    'status': event_status,
                                    'data': data,
                                    'hash': event_hash
                                }
                                self.log_message.emit(f"[{get_timestamp()}] Found recent status for group '{group}': {event_status}")
                            else:
                                self.log_message.emit(f"[{get_timestamp()}] Skipping already processed event for group '{group}'")

                    except json.JSONDecodeError as e:
                        self.log_message.emit(f"[{get_timestamp()}] Error parsing status data for group '{group}': {e}")
                else:
                    self.log_message.emit(f"[{get_timestamp()}] No status events found for group '{group}'")

            except Exception as e:
                self.log_message.emit(f"[{get_timestamp()}] Error accessing status key '{status_key}': {e}")

        # Process and emit status for each group (including username channel)
        for group in channels_to_load:
            if group in group_found_status:
                # Found a recent event for this group
                status = group_found_status[group]['status']
                data = group_found_status[group]['data']
                event_hash = group_found_status[group]['hash']

                # Mark as processed and emit
                self.mark_event_processed(event_hash)
                self.group_status_updated.emit(group, status, data)
                self.process_ticket_info(data, group)

                # Update group status tracking
                self.group_statuses[group] = status
            else:
                # No recent event found, default to normal
                self.log_message.emit(f"[{get_timestamp()}] No recent status found for group '{group}', defaulting to normal")
                default_data = {'group': group, 'status': 'normal'}
                self.group_status_updated.emit(group, 'normal', default_data)

                # Update group status tracking
                self.group_statuses[group] = 'normal'

        # Calculate and emit the highest priority status across all user groups
        overall_status = self.get_highest_priority_status()
        self.current_overall_status = overall_status
        self.status_updated.emit(overall_status)
        self.log_message.emit(f"[{get_timestamp()}] Initial overall status set to '{overall_status}' based on priority across all user groups")
    
    def process_ticket_info(self, data, group):
        """Extract and process ticket information from a message"""
        # Check if this is a ticket message with required fields or has busylight_pop_url
        if ('ticket' in data and 'status' in data) or 'busylight_pop_url' in data:
            ticket_info = {
                'ticket': data.get('ticket', ''),
                'summary': data.get('summary', ''),
                'busylight_pop_url': data.get('busylight_pop_url', ''),
                'group': group
            }

            # Emit the ticket info for the main app to handle
            if ticket_info['ticket'] or ticket_info['busylight_pop_url']:
                ticket_id = ticket_info['ticket'] if ticket_info['ticket'] else 'URL-only'
                self.log_message.emit(f"[{get_timestamp()}] Ticket information received: #{ticket_id}")
                self.ticket_received.emit(ticket_info)

    def set_users_list(self, users):
        """Set the list of users to subscribe to for presence status updates"""
        self.all_users = [u['username'] for u in users] if users else []
        self.log_message.emit(f"[{get_timestamp()}] User list set with {len(self.all_users)} users")

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
        'funky': Ring.Funky,
        'fairytale': Ring.FairyTale,
        'kuandotrain': Ring.KuandoTrain,
        'telephoneoriginal': Ring.TelephoneOriginal,
        'telephonenordic': Ring.TelephoneNordic,
        'telephonepickmeup': Ring.TelephonePickMeUp,
        'openoffice': Ring.OpenOffice,
        'buzz': Ring.Buzz
    }

    # User-friendly alert tone names for display
    RINGTONE_NAMES = {
        'quiet': 'Quiet',
        'funky': 'Funky',
        'fairytale': 'Fairy Tale',
        'kuandotrain': 'Kuando Train',
        'telephoneoriginal': 'Telephone (Original)',
        'telephonenordic': 'Telephone (Nordic)',
        'telephonepickmeup': 'Telephone (Pick Me Up)',
        'openoffice': 'OpenOffice',
        'buzz': 'Buzz'
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

        # Always allow simulation mode (UI always updates regardless of physical device)
        self.allow_simulation = True

        # Initialize reconnect timer
        self.reconnect_timer = QTimer(self)
        self.reconnect_timer.timeout.connect(self.try_connect_device)
        
        # Initialize state maintenance timer to refresh the light state every 10 seconds
        self.state_maintenance_timer = QTimer(self)
        self.state_maintenance_timer.timeout.connect(self.refresh_light_state)
        self.state_maintenance_timer.start(10000)  # 10 second interval for better device reconnection on macOS
        
        # Initialize effect timer for blinking and other effects
        self.effect_timer = QTimer(self)
        self.effect_timer.timeout.connect(self.update_effect)

        # Initialize flash timer for alert flash completion
        self.flash_completion_timer = None
        self.flash_timer = None

        # Explicitly connect and emit initial device status
        QTimer.singleShot(0, self.try_connect_device)
        
        # Track group statuses
        self.group_statuses = {}  # {group: {status, timestamp, data}}
        self.group_widgets = {}   # {group: {widget, status_label, timestamp_label}}
    
    def refresh_light_state(self):
        """Refresh the light state to keep it active"""
        # Check if devices are actually available (works better on macOS than exception-based detection)
        try:
            if USE_OMEGA:
                available_devices = Busylight_Omega.available_lights()
            else:
                available_devices = Light.available_lights()

            device_count = len(available_devices) if available_devices else 0

            # If we have a light object but no devices are available, device was unplugged
            if self.light is not None and device_count == 0:
                self.light = None
                self.log_message.emit(f"[{get_timestamp()}] Device unplugged, will try to reconnect...")
                self.device_status_changed.emit(False, "")
                self.try_connect_device()
                return

            # If we don't have a light but devices ARE available, try to connect
            if self.light is None and device_count > 0:
                self.log_message.emit(f"[{get_timestamp()}] Device detected, attempting to connect...")
                self.try_connect_device()
                return

            # If we have a light and it's not "off", maintain the state
            if self.light is not None and self.current_status != "off":
                try:
                    # On Windows during alert, only refresh the color, not the ringtone
                    if platform.system() == "Windows" and self.current_status == "alert":
                        # Just refresh the color to keep the light active
                        status_colors = self.get_status_colors()
                        if self.current_status in status_colors:
                            color = status_colors[self.current_status]
                            try:
                                self.light.on(color)
                            except Exception:
                                pass
                        return

                    # Reapply the current status to maintain state, but without logging
                    self.set_status(self.current_status, log_action=False)
                except Exception:
                    # Operation failed, invalidate and reconnect
                    self.light = None
                    self.log_message.emit(f"[{get_timestamp()}] Lost connection to light during refresh, will try to reconnect...")
                    self.device_status_changed.emit(False, "")
                    self.try_connect_device()

        except Exception as e:
            # If we can't even enumerate devices, something is wrong
            self.log_message.emit(f"[{get_timestamp()}] Error checking for devices: {e}")
    
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
    
    def apply_brightness(self, color):
        """Apply brightness scaling to a color tuple.

        Args:
            color: RGB tuple (0-255, 0-255, 0-255)

        Returns:
            RGB tuple with brightness applied
        """
        # Load brightness setting (10-100%)
        settings = QSettings("Busylight", "BusylightController")
        brightness = settings.value("busylight/brightness", 100, type=int)

        # Apply brightness as a multiplier (convert percentage to 0.0-1.0)
        multiplier = brightness / 100.0

        # Scale each RGB component
        return (
            int(color[0] * multiplier),
            int(color[1] * multiplier),
            int(color[2] * multiplier)
        )

    def set_status(self, status, log_action=False):
        """Set light status with optional logging and UI updates."""
        # Cancel any active flash timer to prevent conflicts when status changes
        if hasattr(self, 'flash_timer') and self.flash_timer and self.flash_timer.isActive():
            self.flash_timer.stop()

        # Normalize status first
        if status not in self.COLOR_MAP:
            status = 'normal'

        # Always update current status and UI, regardless of physical device availability
        self.current_status = status
        color = self.COLOR_MAP[status]

        # Apply brightness scaling
        color = self.apply_brightness(color)

        # Always emit color changed signal for UI updates (tray icon, status display, etc.)
        self.color_changed.emit(status)

        # If no physical device is available, return after UI updates
        if not self.light and not self.simulation_mode:
            if log_action:
                self.log_message.emit(f"[{get_timestamp()}] No light device found (UI updated)")
            return
        
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

        # Special case for alert status - use configured alert tone if enabled and no manual ringtone is set
        # This ensures alerts play a sound if the user has enabled alert tones
        if status == 'alert' and self.current_ringtone == 'off':
            # Load settings to check if alert tones are enabled
            settings = QSettings("Busylight", "BusylightController")
            alert_tone_enabled = settings.value("busylight/alert_tone_enabled", True, type=bool)

            if alert_tone_enabled:
                # Load the configured alert tone and volume from settings
                configured_ringtone = settings.value("busylight/ringtone", "funky")
                ringtone = self.RINGTONES.get(configured_ringtone, Ring.Funky)
                volume = settings.value("busylight/volume", 7, type=int)
            else:
                # Alert tones disabled, use Ring.Off
                ringtone = Ring.Off
                volume = 0

            # Check if flash on alert is enabled
            flash_enabled = settings.value("busylight/flash_enabled", False, type=bool)
            if flash_enabled:
                # Cancel any pending flash timer from previous alert
                if self.flash_completion_timer and self.flash_completion_timer.isActive():
                    self.flash_completion_timer.stop()

                # Load flash settings
                flash_speed = settings.value("busylight/flash_speed", "medium")
                flash_count = settings.value("busylight/flash_count", 3, type=int)
                flash_color_hex = settings.value("busylight/flash_color", "#FFFFFF")

                # Convert hex color to RGB tuple
                flash_color = QColor(flash_color_hex)
                flash_rgb = (flash_color.red(), flash_color.green(), flash_color.blue())

                # Apply brightness to flash color
                flash_rgb = self.apply_brightness(flash_rgb)

                # Get speed interval
                try:
                    speed_obj = Speed(flash_speed)
                    interval = speed_obj.duty_cycle
                except ValueError:
                    interval = 0.5  # Default to medium speed

                if log_action:
                    self.log_message.emit(f"[{get_timestamp()}] Flashing alert {flash_count} times")

                # Use a simpler approach: manually toggle colors with QTimer
                flash_state = {'current_flash': 0, 'showing_alert_color': True}

                def toggle_flash():
                    try:
                        if flash_state['showing_alert_color']:
                            # Switch to flash color
                            self.light.on(flash_rgb)
                            flash_state['showing_alert_color'] = False
                        else:
                            # Switch to alert color
                            self.light.on(color)
                            flash_state['showing_alert_color'] = True
                            flash_state['current_flash'] += 1

                        # Check if we've completed all flashes
                        if flash_state['current_flash'] >= flash_count:
                            # Stop the flash timer
                            if hasattr(self, 'flash_timer') and self.flash_timer:
                                self.flash_timer.stop()

                            # Set solid color with ringtone after a short delay
                            def set_solid_with_ringtone():
                                # Only set if still in alert status
                                if self.current_status == 'alert':
                                    try:
                                        # On Windows, ensure flash timer is completely stopped
                                        if platform.system() == "Windows":
                                            if hasattr(self, 'flash_timer') and self.flash_timer:
                                                if self.flash_timer.isActive():
                                                    self.flash_timer.stop()
                                                self.flash_timer.deleteLater()
                                                self.flash_timer = None

                                        # Extract ringtone ID
                                        ringtone_id = (ringtone >> 3) & 0xF if ringtone else 0

                                        if platform.system() == "Windows":
                                            # On Windows, send ringtone WITHOUT color to avoid interference
                                            # This matches the MQTT pattern that works correctly
                                            instruction = Instruction.Jump(
                                                ringtone=ringtone_id,
                                                volume=volume,
                                                update=1,
                                                repeat=0,
                                                on_time=0,
                                                off_time=0,
                                            )

                                            with self.light.batch_update():
                                                self.light.command.line0 = instruction.value

                                            # Set color separately after ringtone command
                                            self.light.on(color)
                                        else:
                                            # On macOS, use the existing approach that works
                                            instruction = Instruction.Jump(
                                                target=0,
                                                color=color,
                                                on_time=0,
                                                off_time=0,
                                                ringtone=ringtone_id,
                                                volume=volume,
                                                update=1,
                                            )

                                            with self.light.batch_update():
                                                self.light.color = color
                                                self.light.command.line0 = instruction.value

                                        # Add keepalive task to maintain device state
                                        # Now safe on Windows since ringtone is separate from color
                                        if hasattr(self.light, 'add_task'):
                                            import asyncio
                                            async def _keepalive(light, interval: int = 0xF) -> None:
                                                interval = interval & 0x0F
                                                sleep_interval = round(interval / 2)
                                                from busylight.lights.kuando._busylight import Instruction as KInstruction
                                                command = KInstruction.KeepAlive(interval).value
                                                while True:
                                                    with light.batch_update():
                                                        light.command.line0 = command
                                                    await asyncio.sleep(sleep_interval)

                                            self.light.add_task("keepalive", _keepalive)
                                    except Exception as e:
                                        if log_action:
                                            self.log_message.emit(f"[{get_timestamp()}] Error setting solid after flash: {e}")

                            # Schedule solid color after flash completes
                            self.flash_completion_timer = QTimer.singleShot(100, set_solid_with_ringtone)

                    except Exception as e:
                        if log_action:
                            self.log_message.emit(f"[{get_timestamp()}] Error during flash: {e}")

                # Create and start flash timer
                self.flash_timer = QTimer(self)
                self.flash_timer.timeout.connect(toggle_flash)
                self.flash_timer.start(int(interval * 1000))  # Convert to milliseconds

                # Start with the alert color immediately
                try:
                    self.light.on(color)
                except Exception as e:
                    if log_action:
                        self.log_message.emit(f"[{get_timestamp()}] Error starting flash: {e}")

                # Return early since flash is handling the light
                return

        try:
            # Extract ringtone ID
            ringtone_id = (ringtone >> 3) & 0xF if ringtone else 0

            if platform.system() == "Windows":
                # On Windows, send ringtone WITHOUT color to avoid interference
                # This matches the MQTT pattern that works correctly
                instruction = Instruction.Jump(
                    ringtone=ringtone_id,
                    volume=volume,
                    update=1,
                    repeat=0,
                    on_time=0,
                    off_time=0,
                )

                # Create command buffer and set the instruction
                cmd_buffer = CommandBuffer()
                cmd_buffer.line0 = instruction.value

                # Write ringtone command first
                with self.light.batch_update():
                    self.light.command.line0 = instruction.value

                # Set color separately after ringtone command
                self.light.on(color)
            else:
                # On macOS, use the existing approach that works
                instruction = Instruction.Jump(
                    target=0,
                    color=color,
                    on_time=0,
                    off_time=0,
                    ringtone=ringtone_id,
                    volume=volume,
                    update=1,
                )

                # Create command buffer and set the instruction
                cmd_buffer = CommandBuffer()
                cmd_buffer.line0 = instruction.value

                # Write directly to the device
                with self.light.batch_update():
                    self.light.color = color
                    self.light.command.line0 = instruction.value

            # Apply the effect if one is set
            if self.current_effect == "none" or status == "off":
                # Stop any running effect timer
                if self.effect_timer.isActive():
                    self.effect_timer.stop()
                # For off status, we need to turn off the light
                if status == "off":
                    self.light.off()
                # For solid color with no ringtone changes, the instruction above already set it
            elif self.current_effect == "blink":
                # For blinking, use timer-based approach to preserve ringtone
                # Native blink would overwrite our ringtone instruction
                if not self.effect_timer.isActive():
                    self.effect_timer.start(500)  # Blink every 500ms

            # Add keepalive task for Kuando lights
            if hasattr(self.light, 'add_task'):
                # Import keepalive function if available
                try:
                    import asyncio
                    async def _keepalive(light, interval: int = 0xF) -> None:
                        interval = interval & 0x0F
                        sleep_interval = round(interval / 2)
                        from busylight.lights.kuando._busylight import Instruction as KInstruction
                        command = KInstruction.KeepAlive(interval).value
                        while True:
                            with light.batch_update():
                                light.command.line0 = command
                            await asyncio.sleep(sleep_interval)

                    self.light.add_task("keepalive", _keepalive)
                except Exception:
                    pass  # Keepalive not available, that's okay
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
        self.list_item_to_group = {}
        self.group_event_history = {}
        # User presence status tracking (display only, does not affect busylight)
        self.user_statuses = {}  # {username: {status, groups, last_update}}
        self.user_widgets = {}   # {username: {item, dot_label}}
        self.current_user_status = USER_STATUS_AVAILABLE
        self.all_users = []  # List of all users from API
        self.redis_worker = None
        self.worker_thread = None
        self.light_controller = None
        self.tray_icon = None
        self.tray_blink_timer = None
        self.is_tray_visible = True

        # Initialize settings
        self.settings = QSettings("Busylight", "BusylightController")

        # Initialize logging system
        logger, log_signal_emitter = setup_logging()
        self.log_signal_emitter = log_signal_emitter

        # Connect log signal to UI handler
        self.log_signal_emitter.log_message.connect(self.on_log_message_received)

        # Flag to prevent TTS during app initialization
        self.is_initializing = True

        # Initialize TTS manager
        self.tts_manager = TTSManager(self)
        self.tts_manager.tts_completed.connect(
            lambda msg_type: self.add_log(f"[{get_timestamp()}] TTS completed: {msg_type}")
        )
        self.tts_manager.tts_error.connect(
            lambda err: self.add_log(f"[{get_timestamp()}] TTS error: {err}")
        )
        self.tts_manager.start()
        self.add_log(f"[{get_timestamp()}] TTS Manager started")

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

        # Note: current_ringtone stays as "off" by default
        # The configured alert ringtone is loaded from settings only when an alert occurs

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
        # Prevent tabs from expanding to fill space (keeps them left-aligned)
        self.main_tab_widget.tabBar().setExpanding(False)

        # Connect tab change signal for logging
        self.main_tab_widget.currentChanged.connect(self.on_tab_changed)
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
        self.create_activity_log_tab(colors)

        # Add help button to tab bar corner with proper spacing
        help_container = QWidget()
        help_layout = QHBoxLayout(help_container)
        help_layout.setContentsMargins(8, 2, 12, 2)  # left, top, right, bottom margins - reduced for vertical centering
        help_layout.setSpacing(0)
        help_layout.setAlignment(Qt.AlignVCenter)  # Vertically center the button

        self.help_button = QPushButton("?")
        self.help_button.setFixedSize(32, 32)
        self.help_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {colors['accent_blue']};
                color: {colors['bg_primary']};
                border: none;
                border-radius: 16px;
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors['hover_bg']};
            }}
        """)
        self.help_button.setToolTip("Help & About")
        self.help_button.clicked.connect(self.show_help_dialog)

        help_layout.addWidget(self.help_button)
        self.main_tab_widget.setCornerWidget(help_container, Qt.TopRightCorner)

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

            # Tab 1: Groups (combined My Groups and All Groups)
            groups_tab = QWidget()
            groups_layout = QVBoxLayout(groups_tab)

            # Get user's groups and other groups
            my_groups = self.redis_info.get('groups', []) if self.redis_info else []
            all_groups_list = self.redis_info.get('all_groups', []) if self.redis_info else []
            user_groups_set = set(my_groups)
            other_groups = [g for g in all_groups_list if g not in user_groups_set]

            # Create combined split panel for all groups
            self.groups_splitter = self.create_combined_groups_panel_layout(my_groups, other_groups, colors)
            groups_layout.addWidget(self.groups_splitter)

            # Tab 2: Users (split panel view - display only)
            users_tab = QWidget()
            users_layout = QVBoxLayout(users_tab)

            # Create split panel for users
            self.users_splitter = self.create_users_split_panel_layout(colors)
            users_layout.addWidget(self.users_splitter)

            # Add tabs to the tab widget
            tab_widget.addTab(groups_tab, "Groups")
            tab_widget.addTab(users_tab, "Users")

            # Add Custom Status Update button and My Status selector above tabs
            button_container = QWidget()
            button_layout = QHBoxLayout(button_container)
            button_layout.setContentsMargins(0, 0, 0, 10)

            # My Status label and combo box
            my_status_label = QLabel("My Status:")
            my_status_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; font-weight: 600;")
            button_layout.addWidget(my_status_label)

            self.user_status_combo = QComboBox()
            self.user_status_combo.addItem("Available", USER_STATUS_AVAILABLE)
            self.user_status_combo.addItem("Busy", USER_STATUS_BUSY)
            self.user_status_combo.addItem("Away", USER_STATUS_AWAY)
            self.user_status_combo.addItem("Break", USER_STATUS_BREAK)
            self.user_status_combo.setStyleSheet(f"""
                QComboBox {{
                    background-color: {colors['input_bg']};
                    color: {colors['text_primary']};
                    border: 1px solid {colors['border_secondary']};
                    border-radius: 6px;
                    padding: 6px 12px;
                    font-size: 13px;
                    min-width: 100px;
                }}
                QComboBox:hover {{
                    border-color: {colors['accent_blue']};
                }}
                QComboBox::drop-down {{
                    border: none;
                    padding-right: 8px;
                }}
            """)
            self.user_status_combo.currentIndexChanged.connect(self.on_user_status_combo_changed)
            button_layout.addWidget(self.user_status_combo)

            button_layout.addStretch()

            custom_status_btn = QPushButton("Status Update...")
            custom_status_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {colors['accent_blue']};
                    color: {colors['bg_primary']};
                    border: none;
                    padding: 10px 20px;
                    border-radius: 6px;
                    font-weight: 600;
                    font-size: 14px;
                    min-width: 180px;
                }}
                QPushButton:hover {{
                    background-color: {colors['hover_bg']};
                }}
            """)
            custom_status_btn.setToolTip("Set status on any queue or group")
            custom_status_btn.clicked.connect(self.show_custom_status_dialog)
            button_layout.addWidget(custom_status_btn)

            groups_main_layout.addWidget(button_container)
            groups_main_layout.addWidget(tab_widget)
            groups_main.setLayout(groups_main_layout)

            # Store references
            self.groups_tab_widget = tab_widget
            self.groups_main_layout = groups_main_layout
            self.groups_main = groups_main
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
        self.apply_button = QPushButton(APPLY_SETTINGS_BUTTON_TEXT)
        self.apply_button.clicked.connect(lambda: self.apply_config_settings())
        self.apply_button.setStyleSheet(f"""
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
            QPushButton:disabled {{
                background: {colors['hover_bg']};
                color: {colors['text_secondary']};
            }}
        """)
        config_layout.addWidget(self.apply_button)

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
        tts_layout.setLabelAlignment(Qt.AlignLeft)
        tts_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        tts_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        tts_layout.setSpacing(12)

        # TTS Enabled checkbox
        self.tts_enabled_checkbox_settings = QCheckBox()
        self.tts_enabled_checkbox_settings.setStyleSheet(checkbox_style)
        self.tts_enabled_checkbox_settings.setChecked(settings.value("tts/enabled", False, type=bool))
        tts_layout.addRow("Enable TTS:", self.tts_enabled_checkbox_settings)

        # TTS Slow checkbox
        self.tts_rate_label_settings = QLabel("Slow Speech:")
        self.tts_rate_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_slow_checkbox_settings = QCheckBox()
        self.tts_slow_checkbox_settings.setChecked(settings.value("tts/slow", False, type=bool))
        self.tts_slow_checkbox_settings.setStyleSheet(checkbox_style)
        tts_layout.addRow(self.tts_rate_label_settings, self.tts_slow_checkbox_settings)

        # TTS Volume slider
        self.tts_volume_label_settings = QLabel("Volume:")
        self.tts_volume_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_volume_slider_settings = QSlider(Qt.Horizontal)
        self.tts_volume_slider_settings.setRange(0, 100)
        self.tts_volume_slider_settings.setValue(int(settings.value("tts/volume", 0.9, type=float) * 100))
        self.tts_volume_slider_settings.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {colors['input_border']};
                height: 8px;
                background: {colors['input_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent_blue']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
        """)
        tts_layout.addRow(self.tts_volume_label_settings, self.tts_volume_slider_settings)

        # TTS Voice dropdown
        self.tts_voice_label_settings = QLabel("Voice:")
        self.tts_voice_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_voice_combo_settings = QComboBox()
        self.tts_voice_combo_settings.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
        """)

        # Populate voices
        english_voices = get_available_english_voices()
        saved_voice_id = settings.value("tts/voice_id", None)
        selected_index = 0

        for idx, voice in enumerate(english_voices):
            self.tts_voice_combo_settings.addItem(voice['name'], voice['id'])
            if saved_voice_id and voice['id'] == saved_voice_id:
                selected_index = idx

        if english_voices:
            self.tts_voice_combo_settings.setCurrentIndex(selected_index)

        tts_layout.addRow(self.tts_voice_label_settings, self.tts_voice_combo_settings)

        # Custom test text input
        self.tts_test_text_label_settings = QLabel("Test Text:")
        self.tts_test_text_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.tts_test_text_input_settings = QLineEdit()
        self.tts_test_text_input_settings.setPlaceholderText("Enter text to test voice (optional)")
        self.tts_test_text_input_settings.setStyleSheet(f"""
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
        tts_layout.addRow(self.tts_test_text_label_settings, self.tts_test_text_input_settings)

        # Test button for Settings dialog
        self.tts_test_button_settings = QPushButton("Test Voice")
        self.tts_test_button_settings.setToolTip("Test the TTS settings with custom or default text")
        self.tts_test_button_settings.clicked.connect(self.test_tts_settings_dialog)
        self.tts_test_button_settings.setStyleSheet(f"""
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
        tts_layout.addRow("", self.tts_test_button_settings)

        # Store TTS widgets for show/hide in settings dialog
        self.tts_settings_widgets = [
            self.tts_rate_label_settings, self.tts_slow_checkbox_settings,
            self.tts_volume_label_settings, self.tts_volume_slider_settings,
            self.tts_voice_label_settings, self.tts_voice_combo_settings,
            self.tts_test_text_label_settings, self.tts_test_text_input_settings,
            self.tts_test_button_settings
        ]

        # Connect checkbox to toggle visibility
        self.tts_enabled_checkbox_settings.stateChanged.connect(self.toggle_tts_settings_visibility)

        # Set initial visibility
        self.toggle_tts_settings_visibility()

        layout.addWidget(tts_group)

        # URL Configuration Group
        url_group = QGroupBox("URL Handler Configuration")
        url_group.setFont(bold_font)
        url_group.setStyleSheet(group_style)
        url_layout = QFormLayout(url_group)
        url_layout.setLabelAlignment(Qt.AlignLeft)
        url_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        url_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        url_layout.setSpacing(12)

        self.url_enabled_checkbox = QCheckBox()
        self.url_enabled_checkbox.setStyleSheet(checkbox_style)
        self.url_enabled_checkbox.setChecked(settings.value("url/enabled", False, type=bool))
        url_layout.addRow("Open URLs:", self.url_enabled_checkbox)

        layout.addWidget(url_group)

        # Busylight Configuration Group
        busylight_group = QGroupBox("Busylight Alert Tone Configuration")
        busylight_group.setFont(bold_font)
        busylight_group.setStyleSheet(group_style)
        busylight_layout = QFormLayout(busylight_group)
        busylight_layout.setLabelAlignment(Qt.AlignLeft)
        busylight_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        busylight_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        busylight_layout.setSpacing(12)

        # Alert Tone Enabled checkbox
        self.alert_tone_enabled_checkbox_settings = QCheckBox()
        self.alert_tone_enabled_checkbox_settings.setStyleSheet(checkbox_style)
        self.alert_tone_enabled_checkbox_settings.setChecked(settings.value("busylight/alert_tone_enabled", True, type=bool))
        busylight_layout.addRow("Enable Alert Tone:", self.alert_tone_enabled_checkbox_settings)

        # Alert Tone dropdown
        self.ringtone_label_settings = QLabel("Alert Tone:")
        self.ringtone_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.ringtone_combo_settings = QComboBox()
        self.ringtone_combo_settings.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {colors['text_secondary']};
                margin-right: 4px;
            }}
        """)

        # Populate ringtones using the RINGTONE_NAMES from LightController
        saved_ringtone = settings.value("busylight/ringtone", "funky")
        selected_index = 0

        for idx, (ringtone_key, ringtone_name) in enumerate(LightController.RINGTONE_NAMES.items()):
            self.ringtone_combo_settings.addItem(ringtone_name, ringtone_key)
            if ringtone_key == saved_ringtone:
                selected_index = idx

        self.ringtone_combo_settings.setCurrentIndex(selected_index)
        self.ringtone_combo_settings.setToolTip("Select the alert tone to play when an alert status is triggered")

        busylight_layout.addRow(self.ringtone_label_settings, self.ringtone_combo_settings)

        # Alert Tone Volume slider
        self.ringtone_volume_label_settings = QLabel("Volume:")
        self.ringtone_volume_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.ringtone_volume_slider_settings = QSlider(Qt.Horizontal)
        self.ringtone_volume_slider_settings.setRange(0, 7)  # Volume is 3-bit: 0-7
        self.ringtone_volume_slider_settings.setValue(settings.value("busylight/volume", 7, type=int))
        self.ringtone_volume_slider_settings.setToolTip("Set the alert tone volume (0-7)")
        self.ringtone_volume_slider_settings.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {colors['input_border']};
                height: 8px;
                background: {colors['input_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent_blue']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
        """)

        # Connect volume slider to real-time update
        self.ringtone_volume_slider_settings.valueChanged.connect(self.update_volume_preview)

        busylight_layout.addRow(self.ringtone_volume_label_settings, self.ringtone_volume_slider_settings)

        # Test Alert Tone button
        self.test_ringtone_button = QPushButton("Test Alert Tone")
        self.test_ringtone_button.setToolTip("Play the selected alert tone for 3 seconds")
        self.test_ringtone_button.clicked.connect(self.test_ringtone)
        self.test_ringtone_button.setStyleSheet(f"""
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
        busylight_layout.addRow("", self.test_ringtone_button)

        # Store alert tone widgets for show/hide
        self.alert_tone_settings_widgets = [
            self.ringtone_label_settings, self.ringtone_combo_settings,
            self.ringtone_volume_label_settings, self.ringtone_volume_slider_settings,
            self.test_ringtone_button
        ]

        # Connect checkbox to toggle visibility
        self.alert_tone_enabled_checkbox_settings.stateChanged.connect(self.toggle_alert_tone_settings_visibility)

        # Set initial visibility
        self.toggle_alert_tone_settings_visibility()

        layout.addWidget(busylight_group)

        # Flash Alert Configuration Group
        flash_group = QGroupBox("Flash Alert Configuration")
        flash_group.setFont(bold_font)
        flash_group.setStyleSheet(group_style)
        flash_layout = QFormLayout(flash_group)
        flash_layout.setLabelAlignment(Qt.AlignLeft)
        flash_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        flash_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        flash_layout.setSpacing(12)

        # Enable Flash on Alert checkbox
        self.flash_enabled_checkbox_settings = QCheckBox()
        self.flash_enabled_checkbox_settings.setStyleSheet(checkbox_style)
        self.flash_enabled_checkbox_settings.setChecked(settings.value("busylight/flash_enabled", False, type=bool))
        self.flash_enabled_checkbox_settings.setToolTip("Flash the light when an alert is triggered")
        flash_layout.addRow("Enable Flash on Alert:", self.flash_enabled_checkbox_settings)

        # Flash Speed dropdown
        self.flash_speed_label_settings = QLabel("Flash Speed:")
        self.flash_speed_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")
        self.flash_speed_combo_settings = QComboBox()
        self.flash_speed_combo_settings.setStyleSheet(f"""
            QComboBox {{
                padding: 8px 12px;
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                background: {colors['input_bg']};
                font-size: 13px;
                color: {colors['text_secondary']};
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {colors['text_secondary']};
                margin-right: 4px;
            }}
        """)

        # Add speed options
        self.flash_speed_combo_settings.addItem("Slow (0.75s)", "slow")
        self.flash_speed_combo_settings.addItem("Medium (0.5s)", "medium")
        self.flash_speed_combo_settings.addItem("Fast (0.25s)", "fast")

        saved_flash_speed = settings.value("busylight/flash_speed", "medium")
        flash_speed_index = {"slow": 0, "medium": 1, "fast": 2}.get(saved_flash_speed, 1)
        self.flash_speed_combo_settings.setCurrentIndex(flash_speed_index)
        self.flash_speed_combo_settings.setToolTip("Speed at which the light flashes")

        flash_layout.addRow(self.flash_speed_label_settings, self.flash_speed_combo_settings)

        # Flash Count slider
        self.flash_count_label_settings = QLabel("Flash Count:")
        self.flash_count_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")

        # Create horizontal layout for slider and value label
        flash_count_layout = QHBoxLayout()
        self.flash_count_slider_settings = QSlider(Qt.Horizontal)
        self.flash_count_slider_settings.setRange(1, 10)
        self.flash_count_slider_settings.setValue(settings.value("busylight/flash_count", 3, type=int))
        self.flash_count_slider_settings.setToolTip("Number of times to flash (1-10)")
        self.flash_count_slider_settings.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {colors['input_border']};
                height: 8px;
                background: {colors['input_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent_blue']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
        """)

        # Add value label next to slider
        self.flash_count_value_label_settings = QLabel(str(settings.value("busylight/flash_count", 3, type=int)))
        self.flash_count_value_label_settings.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 14px; min-width: 30px;")
        self.flash_count_slider_settings.valueChanged.connect(
            lambda v: self.flash_count_value_label_settings.setText(str(v))
        )

        flash_count_layout.addWidget(self.flash_count_slider_settings)
        flash_count_layout.addWidget(self.flash_count_value_label_settings)

        flash_layout.addRow(self.flash_count_label_settings, flash_count_layout)

        # Flash Secondary Color picker
        self.flash_color_label_settings = QLabel("Flash Color:")
        self.flash_color_label_settings.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")

        # Create horizontal layout for color preview and button
        flash_color_layout = QHBoxLayout()

        # Get saved color or default to white
        saved_flash_color = settings.value("busylight/flash_color", "#FFFFFF")
        self.current_flash_color = QColor(saved_flash_color)

        # Color preview square
        self.flash_color_preview_settings = QLabel()
        self.flash_color_preview_settings.setFixedSize(30, 30)
        self.flash_color_preview_settings.setStyleSheet(f"""
            QLabel {{
                background-color: {self.current_flash_color.name()};
                border: 2px solid {colors['input_border']};
                border-radius: 4px;
            }}
        """)

        # Color picker button
        self.flash_color_button_settings = QPushButton("Choose Color")
        self.flash_color_button_settings.setToolTip("Select the secondary color to flash")
        self.flash_color_button_settings.clicked.connect(self.choose_flash_color)
        self.flash_color_button_settings.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 6px 12px;
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

        flash_color_layout.addWidget(self.flash_color_preview_settings)
        flash_color_layout.addWidget(self.flash_color_button_settings)
        flash_color_layout.addStretch()

        flash_layout.addRow(self.flash_color_label_settings, flash_color_layout)

        # Test Flash button
        self.test_flash_button = QPushButton("Test Flash")
        self.test_flash_button.setToolTip("Preview the flash effect with current settings")
        self.test_flash_button.clicked.connect(self.test_flash)
        self.test_flash_button.setStyleSheet(f"""
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
        flash_layout.addRow("", self.test_flash_button)

        # Store flash settings widgets for show/hide
        self.flash_settings_widgets = [
            self.flash_speed_label_settings, self.flash_speed_combo_settings,
            self.flash_count_label_settings, flash_count_layout.itemAt(0).widget(),
            flash_count_layout.itemAt(1).widget(),
            self.flash_color_label_settings, self.flash_color_preview_settings,
            self.flash_color_button_settings, self.test_flash_button
        ]

        # Connect checkbox to toggle visibility
        self.flash_enabled_checkbox_settings.stateChanged.connect(self.toggle_flash_settings_visibility)

        # Set initial visibility
        self.toggle_flash_settings_visibility()

        layout.addWidget(flash_group)

        # Brightness Configuration Group
        brightness_group = QGroupBox("Brightness Control")
        brightness_group.setFont(bold_font)
        brightness_group.setStyleSheet(group_style)
        brightness_layout = QFormLayout(brightness_group)
        brightness_layout.setLabelAlignment(Qt.AlignLeft)
        brightness_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        brightness_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        brightness_layout.setSpacing(12)

        # Brightness slider
        brightness_label = QLabel("Brightness:")
        brightness_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 14px;")

        # Create horizontal layout for slider and value label
        brightness_slider_layout = QHBoxLayout()
        self.brightness_slider_settings = QSlider(Qt.Horizontal)
        self.brightness_slider_settings.setRange(10, 100)  # 10% to 100%
        self.brightness_slider_settings.setValue(settings.value("busylight/brightness", 100, type=int))
        self.brightness_slider_settings.setToolTip("Adjust light brightness (10-100%)")
        self.brightness_slider_settings.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                border: 1px solid {colors['input_border']};
                height: 8px;
                background: {colors['input_bg']};
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: {colors['accent_blue']};
                border: none;
                width: 18px;
                margin: -5px 0;
                border-radius: 9px;
            }}
        """)

        # Add value label next to slider showing percentage
        self.brightness_value_label_settings = QLabel(f"{settings.value('busylight/brightness', 100, type=int)}%")
        self.brightness_value_label_settings.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 14px; min-width: 40px;")

        # Connect to update label and light in real time
        def update_brightness_realtime(value):
            self.brightness_value_label_settings.setText(f"{value}%")
            self.update_brightness_preview(value)

        self.brightness_slider_settings.valueChanged.connect(update_brightness_realtime)

        brightness_slider_layout.addWidget(self.brightness_slider_settings)
        brightness_slider_layout.addWidget(self.brightness_value_label_settings)

        brightness_layout.addRow(brightness_label, brightness_slider_layout)

        # Add help text
        brightness_help = QLabel("Reduce brightness for nighttime use or less distraction")
        brightness_help.setStyleSheet(f"color: {colors['text_muted']}; font-size: 12px; font-style: italic;")
        brightness_help.setWordWrap(True)
        brightness_layout.addRow("", brightness_help)

        layout.addWidget(brightness_group)

        # App Configuration Group
        app_group = QGroupBox("Application Settings")
        app_group.setFont(bold_font)
        app_group.setStyleSheet(group_style)
        app_layout = QFormLayout(app_group)
        app_layout.setLabelAlignment(Qt.AlignLeft)
        app_layout.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        app_layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        app_layout.setSpacing(12)

        self.start_minimized_checkbox = QCheckBox()
        self.start_minimized_checkbox.setStyleSheet(checkbox_style)
        self.start_minimized_checkbox.setChecked(settings.value("app/start_minimized", False, type=bool))
        app_layout.addRow("Start Minimized:", self.start_minimized_checkbox)

        self.autostart_checkbox = QCheckBox()
        self.autostart_checkbox.setStyleSheet(checkbox_style)
        self.autostart_checkbox.setChecked(settings.value("app/autostart", False, type=bool))
        app_layout.addRow("Autostart:", self.autostart_checkbox)

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

    def create_activity_log_tab(self, colors):
        """Create the Activity Log tab with log display and controls"""
        log_tab = QWidget()
        log_layout = QVBoxLayout(log_tab)
        log_layout.setSpacing(12)
        log_layout.setContentsMargins(16, 16, 16, 16)

        # Create control bar at top
        control_bar = QWidget()
        control_layout = QHBoxLayout(control_bar)
        control_layout.setContentsMargins(0, 0, 0, 0)
        control_layout.setSpacing(12)

        # Add title label
        title_label = QLabel("Application Activity Log")
        title_label.setStyleSheet(f"""
            font-size: 18px;
            font-weight: bold;
            color: {colors['text_primary']};
        """)
        control_layout.addWidget(title_label)

        control_layout.addStretch()

        # Add log level filter
        filter_label = QLabel("Show:")
        filter_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 13px;")
        control_layout.addWidget(filter_label)

        self.log_level_filter = QComboBox()
        self.log_level_filter.addItems(["All", "INFO+", "WARNING+", "ERROR"])
        self.log_level_filter.setCurrentIndex(0)
        self.log_level_filter.currentTextChanged.connect(self.apply_log_filter)
        self.log_level_filter.setStyleSheet(f"""
            QComboBox {{
                background: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                border-radius: 6px;
                padding: 6px 12px;
                color: {colors['text_primary']};
                font-size: 13px;
                min-width: 100px;
            }}
            QComboBox:hover {{
                border-color: {colors['accent_blue']};
            }}
            QComboBox::drop-down {{
                border: none;
                padding-right: 8px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid {colors['text_secondary']};
                margin-right: 4px;
            }}
        """)
        control_layout.addWidget(self.log_level_filter)

        # Add Copy button
        copy_button = QPushButton("Copy to Clipboard")
        copy_button.clicked.connect(self.copy_logs_to_clipboard)
        copy_button.setStyleSheet(f"""
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
        """)
        control_layout.addWidget(copy_button)

        # Add Clear button
        clear_button = QPushButton("Clear Log")
        clear_button.clicked.connect(self.clear_activity_log)
        clear_button.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_red']};
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
        """)
        control_layout.addWidget(clear_button)

        log_layout.addWidget(control_bar)

        # Create log widget
        self.log_widget = LogWidget()
        self.log_widget.setStyleSheet(f"""
            QTextEdit {{
                background: {colors['input_bg']};
                border: 1px solid {colors['input_border']};
                border-radius: 8px;
                padding: 12px;
                color: {colors['text_secondary']};
                font-family: 'Monaco', 'Consolas', 'Courier New', monospace;
                font-size: 11px;
                line-height: 1.4;
            }}
        """)
        log_layout.addWidget(self.log_widget)

        # Add info footer
        info_label = QLabel(f"Logs are stored at: {get_log_file_path()} (max 5MB, auto-rotated)")
        info_label.setStyleSheet(f"""
            color: {colors['text_muted']};
            font-size: 11px;
            font-style: italic;
            padding: 4px;
        """)
        info_label.setWordWrap(True)
        log_layout.addWidget(info_label)

        self.main_tab_widget.addTab(log_tab, "Activity Log")

    def setup_tray(self):
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Set a default icon - create a colored circle based on current status
        self.update_tray_icon(self.light_controller.current_status)
        
        self.tray_icon.setToolTip("Busylight Controller")
        
        # Create context menu for the tray
        tray_menu = QMenu()

        # Add "My Status" submenu for user presence status
        my_status_menu = QMenu("My Status", tray_menu)
        self.status_action_available = my_status_menu.addAction("Available")
        self.status_action_available.setCheckable(True)
        self.status_action_available.setChecked(True)  # Default to Available
        self.status_action_available.triggered.connect(lambda: self.set_my_status(USER_STATUS_AVAILABLE))

        self.status_action_busy = my_status_menu.addAction("Busy")
        self.status_action_busy.setCheckable(True)
        self.status_action_busy.triggered.connect(lambda: self.set_my_status(USER_STATUS_BUSY))

        self.status_action_away = my_status_menu.addAction("Away")
        self.status_action_away.setCheckable(True)
        self.status_action_away.triggered.connect(lambda: self.set_my_status(USER_STATUS_AWAY))

        self.status_action_break = my_status_menu.addAction("Break")
        self.status_action_break.setCheckable(True)
        self.status_action_break.triggered.connect(lambda: self.set_my_status(USER_STATUS_BREAK))

        tray_menu.addMenu(my_status_menu)
        tray_menu.addSeparator()

        # Add Custom Status Update action
        custom_status_action = tray_menu.addAction("Custom Status Update...")
        custom_status_action.triggered.connect(self.show_custom_status_dialog)

        tray_menu.addSeparator()

        # Add refresh actions
        refresh_connection_action = tray_menu.addAction("Refresh Connection")
        refresh_connection_action.triggered.connect(self.manually_connect_device)

        refresh_status_action = tray_menu.addAction("Refresh From Redis")
        refresh_status_action.triggered.connect(self.refresh_status_from_redis)

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

    def show_help_dialog(self):
        """Show the help and about dialog"""
        help_dialog = HelpDialog(self)
        help_dialog.exec()

    def show_custom_status_dialog(self):
        """Show the custom status update dialog"""
        logger = get_logger()
        logger.debug("User opened Custom Status Update dialog")
        dialog = CustomStatusDialog(parent=self)
        dialog.exec()

    def get_sorted_groups(self, groups, panel_id):
        """Get groups sorted by user's saved order preference"""
        # Load saved order from QSettings
        settings_key = f"group_order/{panel_id}"
        saved_order = self.settings.value(settings_key, [])

        # If no saved order or it's not a list, return groups as-is
        if not saved_order or not isinstance(saved_order, list):
            return groups

        # Sort groups by saved order, putting new groups at the end
        sorted_groups = []
        remaining_groups = list(groups)

        # First add groups in saved order
        for group_name in saved_order:
            if group_name in remaining_groups:
                sorted_groups.append(group_name)
                remaining_groups.remove(group_name)

        # Then add any new groups that weren't in the saved order
        sorted_groups.extend(remaining_groups)

        return sorted_groups

    def save_group_order(self, list_widget, panel_id):
        """Save the current order of groups from the list widget"""
        group_order = []

        # Iterate through all items in the list widget
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            # Find the group name for this item
            for key, value in self.list_item_to_group.items():
                if value['item'] == item and key.startswith(panel_id):
                    group_order.append(value['group'])
                    break

        # Save to QSettings
        settings_key = f"group_order/{panel_id}"
        self.settings.setValue(settings_key, group_order)

    def toggle_tts_settings_visibility(self):
        """Show or hide TTS configuration controls in Settings dialog"""
        if hasattr(self, 'tts_settings_widgets'):
            is_enabled = self.tts_enabled_checkbox_settings.isChecked()
            for widget in self.tts_settings_widgets:
                widget.setVisible(is_enabled)

    def toggle_alert_tone_settings_visibility(self):
        """Show or hide alert tone configuration controls in Settings dialog"""
        if hasattr(self, 'alert_tone_settings_widgets'):
            is_enabled = self.alert_tone_enabled_checkbox_settings.isChecked()
            for widget in self.alert_tone_settings_widgets:
                widget.setVisible(is_enabled)

    def toggle_flash_settings_visibility(self):
        """Show or hide flash alert configuration controls in Settings dialog"""
        if hasattr(self, 'flash_settings_widgets'):
            is_enabled = self.flash_enabled_checkbox_settings.isChecked()
            for widget in self.flash_settings_widgets:
                widget.setVisible(is_enabled)

    def choose_flash_color(self):
        """Open color picker dialog for flash secondary color"""
        color = QColorDialog.getColor(self.current_flash_color, self, "Choose Flash Color")
        if color.isValid():
            self.current_flash_color = color
            # Update the preview square
            colors = get_adaptive_colors()
            self.flash_color_preview_settings.setStyleSheet(f"""
                QLabel {{
                    background-color: {color.name()};
                    border: 2px solid {colors['input_border']};
                    border-radius: 4px;
                }}
            """)

    def update_brightness_preview(self, brightness_value):
        """Update the light brightness in real time as slider changes (preview only, not saved)"""
        try:
            # Only update if we have a light controller and device
            if not hasattr(self, 'light_controller') or not self.light_controller:
                return
            if not self.light_controller.light:
                return

            # Temporarily update the brightness in QSettings (in memory, not persisted yet)
            settings = QSettings("Busylight", "BusylightController")
            settings.setValue("busylight/brightness", brightness_value)

            # Re-apply current status with the new brightness
            current_status = self.light_controller.current_status
            self.light_controller.set_status(current_status, log_action=False)

            # Note: The brightness change is only in memory via QSettings
            # It will be persisted when user clicks "Apply Settings"

        except Exception as e:
            # Silently handle errors during preview
            pass

    def update_volume_preview(self, volume_value):
        """Update alert tone volume in real-time as slider changes"""
        try:
            # Only update if we have a light controller and device
            if not hasattr(self, 'light_controller') or not self.light_controller:
                return
            if not self.light_controller.light:
                return

            # Temporarily update the volume in QSettings (in memory, not persisted yet)
            settings = QSettings("Busylight", "BusylightController")
            settings.setValue("busylight/volume", volume_value)

            # If currently testing the ringtone, update it with new volume
            # Check if test button shows "Playing..." which means a test is active
            if hasattr(self, 'test_ringtone_button') and self.test_ringtone_button.text() == "Playing...":
                # Get current ringtone
                ringtone_key = self.ringtone_combo_settings.currentData() if hasattr(self, 'ringtone_combo_settings') else None
                if ringtone_key and ringtone_key in LightController.RINGTONES:
                    # Temporarily update the controller's volume
                    self.light_controller.current_volume = volume_value

                    # Re-apply the current status to update the ringtone with new volume
                    current_status = self.light_controller.current_status
                    self.light_controller.set_status(current_status, log_action=False)

            # Note: The volume change is only in memory via QSettings
            # It will be persisted when user clicks "Apply Settings"

        except Exception as e:
            # Silently handle errors during preview
            pass

    def test_ringtone(self):
        """Test the selected alert tone by playing it for 3 seconds"""
        try:
            if not hasattr(self, 'ringtone_combo_settings'):
                return

            # Get the selected alert tone
            ringtone_key = self.ringtone_combo_settings.currentData()
            if not ringtone_key or ringtone_key not in LightController.RINGTONES:
                self.add_log(f"[{get_timestamp()}] Invalid alert tone selection")
                return

            # Check if light is available
            if not self.light_controller or not self.light_controller.light:
                self.add_log(f"[{get_timestamp()}] Busylight device not connected - cannot test alert tone")
                QMessageBox.warning(self, "Device Not Connected",
                                  "Busylight device is not connected. Please connect your device to test the alert tone.")
                return

            ringtone_name = LightController.RINGTONE_NAMES.get(ringtone_key, ringtone_key)
            self.add_log(f"[{get_timestamp()}] Testing alert tone: {ringtone_name}")

            # Disable the test button to prevent multiple clicks
            self.test_ringtone_button.setEnabled(False)
            self.test_ringtone_button.setText("Playing...")

            # Save current light state
            current_color = self.light_controller.current_status
            saved_ringtone = self.light_controller.current_ringtone
            saved_volume = self.light_controller.current_volume

            # Get the selected volume from the slider
            test_volume = self.ringtone_volume_slider_settings.value() if hasattr(self, 'ringtone_volume_slider_settings') else 7

            # Set the test alert tone and volume temporarily
            self.light_controller.current_ringtone = ringtone_key
            self.light_controller.current_volume = test_volume

            # Apply the alert tone by setting the current status (this will trigger the tone)
            if current_color == "off":
                # If light is off, temporarily turn it on to play the alert tone
                self.light_controller.set_status("normal", log_action=False)
            else:
                # Re-apply current status to trigger alert tone
                self.light_controller.set_status(current_color, log_action=False)

            # Schedule alert tone stop after 3 seconds
            def stop_test_ringtone():
                try:
                    # Restore previous alert tone settings
                    self.light_controller.current_ringtone = saved_ringtone
                    self.light_controller.current_volume = saved_volume

                    # Restore original light state
                    self.light_controller.set_status(current_color, log_action=False)

                    # Re-enable the test button
                    self.test_ringtone_button.setEnabled(True)
                    self.test_ringtone_button.setText("Test Alert Tone")

                    self.add_log(f"[{get_timestamp()}] Alert tone test completed")
                except Exception as e:
                    self.add_log(f"[{get_timestamp()}] Error stopping test alert tone: {e}")
                    self.test_ringtone_button.setEnabled(True)
                    self.test_ringtone_button.setText("Test Alert Tone")

            # Use QTimer to stop after 3 seconds
            QTimer.singleShot(3000, stop_test_ringtone)

        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error testing alert tone: {e}")
            if hasattr(self, 'test_ringtone_button'):
                self.test_ringtone_button.setEnabled(True)
                self.test_ringtone_button.setText("Test Alert Tone")

    def test_flash(self):
        """Test the flash effect with current settings"""
        try:
            # Check if device is available
            if not self.light_controller or not self.light_controller.light:
                self.add_log(f"[{get_timestamp()}] Busylight device not connected - cannot test flash")
                QMessageBox.warning(self, "Device Not Connected",
                                  "Busylight device is not connected. Please connect your device to test the flash.")
                return

            # Get flash settings from UI
            flash_speed = self.flash_speed_combo_settings.currentData() if hasattr(self, 'flash_speed_combo_settings') else "medium"
            flash_count = self.flash_count_slider_settings.value() if hasattr(self, 'flash_count_slider_settings') else 3
            flash_color = self.current_flash_color if hasattr(self, 'current_flash_color') else QColor("#FFFFFF")
            flash_rgb = (flash_color.red(), flash_color.green(), flash_color.blue())

            # Apply brightness to flash color
            flash_rgb = self.light_controller.apply_brightness(flash_rgb)

            # Get alert color (red) with brightness
            alert_color = self.light_controller.apply_brightness((255, 0, 0))

            # Get speed interval
            try:
                from busylight.speed import Speed
                speed_obj = Speed(flash_speed)
                interval = speed_obj.duty_cycle
            except (ValueError, ImportError):
                interval = 0.5

            self.add_log(f"[{get_timestamp()}] Testing flash: {flash_count} times at {flash_speed} speed")

            # Disable the test button
            self.test_flash_button.setEnabled(False)
            self.test_flash_button.setText("Flashing...")

            # Save current light state
            current_status = self.light_controller.current_status
            light = self.light_controller.light

            # Flash state tracker
            flash_state = {'current_flash': 0, 'showing_alert_color': True}

            def toggle_test_flash():
                try:
                    if flash_state['showing_alert_color']:
                        # Switch to flash color
                        light.on(flash_rgb)
                        flash_state['showing_alert_color'] = False
                    else:
                        # Switch to alert color
                        light.on(alert_color)
                        flash_state['showing_alert_color'] = True
                        flash_state['current_flash'] += 1

                    # Check if test flash is complete
                    if flash_state['current_flash'] >= flash_count:
                        # Stop the test flash timer
                        if hasattr(self, 'test_flash_timer') and self.test_flash_timer:
                            self.test_flash_timer.stop()

                        # Restore original light state after a short delay
                        def restore_state():
                            try:
                                self.light_controller.set_status(current_status, log_action=False)
                                self.test_flash_button.setEnabled(True)
                                self.test_flash_button.setText("Test Flash")
                                self.add_log(f"[{get_timestamp()}] Flash test completed")
                            except Exception as e:
                                self.add_log(f"[{get_timestamp()}] Error restoring state: {e}")
                                self.test_flash_button.setEnabled(True)
                                self.test_flash_button.setText("Test Flash")

                        QTimer.singleShot(100, restore_state)

                except Exception as e:
                    self.add_log(f"[{get_timestamp()}] Error during test flash: {e}")
                    if hasattr(self, 'test_flash_timer') and self.test_flash_timer:
                        self.test_flash_timer.stop()
                    self.test_flash_button.setEnabled(True)
                    self.test_flash_button.setText("Test Flash")

            # Create and start test flash timer
            self.test_flash_timer = QTimer(self)
            self.test_flash_timer.timeout.connect(toggle_test_flash)
            self.test_flash_timer.start(int(interval * 1000))

            # Start with alert color immediately
            light.on(alert_color)

        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error testing flash: {e}")
            if hasattr(self, 'test_flash_button'):
                self.test_flash_button.setEnabled(True)
                self.test_flash_button.setText("Test Flash")

    def test_tts_settings_dialog(self):
        """Test TTS from the Settings dialog"""
        try:
            # Get custom text if provided, otherwise use default
            custom_text = self.tts_test_text_input_settings.text().strip()
            test_message = custom_text if custom_text else "This is a test of the text to speech system"

            # Get current TTS settings from Settings dialog
            slow = self.tts_slow_checkbox_settings.isChecked()
            volume = self.tts_volume_slider_settings.value() / 100.0
            voice_id = self.tts_voice_combo_settings.currentData()

            # Add to TTS queue for testing
            if hasattr(self, 'tts_manager') and self.tts_manager:
                self.tts_manager.add_to_queue(test_message, slow, volume, voice_id, "test")
                self.add_log(f"[{get_timestamp()}] TTS test started from Settings dialog")
            else:
                self.add_log(f"[{get_timestamp()}] TTS manager not available")

        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error testing TTS: {e}")

    def apply_config_settings(self):
        """Apply settings from the configuration tab"""
        # Disable button and update text to show updating state
        # Button will be re-enabled in complete_initialization()
        if hasattr(self, 'apply_button'):
            self.apply_button.setEnabled(False)
            self.apply_button.setText(APPLY_SETTINGS_BUTTON_TEXT_UPDATING)

        # Save settings from the configuration widgets
        settings = QSettings("Busylight", "BusylightController")

        # Save TTS settings (from Settings dialog widgets)
        if hasattr(self, 'tts_enabled_checkbox_settings'):
            settings.setValue("tts/enabled", self.tts_enabled_checkbox_settings.isChecked())
        if hasattr(self, 'tts_slow_checkbox_settings'):
            settings.setValue("tts/slow", self.tts_slow_checkbox_settings.isChecked())
        if hasattr(self, 'tts_volume_slider_settings'):
            settings.setValue("tts/volume", self.tts_volume_slider_settings.value() / 100.0)
        if hasattr(self, 'tts_voice_combo_settings'):
            settings.setValue("tts/voice_id", self.tts_voice_combo_settings.currentData())

        # Save URL settings
        if hasattr(self, 'url_enabled_checkbox'):
            settings.setValue("url/enabled", self.url_enabled_checkbox.isChecked())

        # Save Busylight settings
        if hasattr(self, 'alert_tone_enabled_checkbox_settings'):
            settings.setValue("busylight/alert_tone_enabled", self.alert_tone_enabled_checkbox_settings.isChecked())
        if hasattr(self, 'ringtone_combo_settings'):
            ringtone_key = self.ringtone_combo_settings.currentData()
            settings.setValue("busylight/ringtone", ringtone_key)
        if hasattr(self, 'ringtone_volume_slider_settings'):
            volume = self.ringtone_volume_slider_settings.value()
            settings.setValue("busylight/volume", volume)
            # Note: We don't apply the alert tone here - it will only play when an alert occurs

        # Save Flash Alert settings
        if hasattr(self, 'flash_enabled_checkbox_settings'):
            settings.setValue("busylight/flash_enabled", self.flash_enabled_checkbox_settings.isChecked())
        if hasattr(self, 'flash_speed_combo_settings'):
            flash_speed = self.flash_speed_combo_settings.currentData()
            settings.setValue("busylight/flash_speed", flash_speed)
        if hasattr(self, 'flash_count_slider_settings'):
            flash_count = self.flash_count_slider_settings.value()
            settings.setValue("busylight/flash_count", flash_count)
        if hasattr(self, 'current_flash_color'):
            settings.setValue("busylight/flash_color", self.current_flash_color.name())

        # Save Brightness settings
        if hasattr(self, 'brightness_slider_settings'):
            brightness = self.brightness_slider_settings.value()
            settings.setValue("busylight/brightness", brightness)
            # Re-apply current status to update brightness on the light
            if hasattr(self, 'light_controller') and self.light_controller:
                self.light_controller.set_status(self.light_controller.current_status, log_action=False)

        # Save app settings
        if hasattr(self, 'start_minimized_checkbox'):
            settings.setValue("app/start_minimized", self.start_minimized_checkbox.isChecked())
        if hasattr(self, 'autostart_checkbox'):
            settings.setValue("app/autostart", self.autostart_checkbox.isChecked())

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
            if not self.worker_thread.wait(3000):
                self.worker_thread.terminate()
                self.worker_thread.wait()

            # Properly delete the old thread
            self.worker_thread.deleteLater()
            self.worker_thread = None

        # Delete old worker
        if hasattr(self, 'redis_worker') and self.redis_worker:
            self.redis_worker.deleteLater()
            self.redis_worker = None

        # Create and start new worker with updated settings
        self.add_log(f"[{get_timestamp()}] Restarting Redis connection with new settings")
        self.start_redis_worker()

        # Complete initialization after a delay to allow historical events to load
        QTimer.singleShot(3000, self.complete_initialization)  # 3 second delay
    
    def update_status_display(self, status):
        # Update the tray icon
        self.update_tray_icon(status)
    
    def add_log(self, message, level="INFO"):
        """Add a message to the log using Python logging

        Args:
            message: The message to log
            level: Log level (DEBUG, INFO, WARNING, ERROR) - default is INFO
        """
        logger = get_logger()

        # Strip timestamp if it's already in the message (for backward compatibility)
        # Old format: [YYYY-MM-DD HH:MM:SS] message
        if message.startswith('[') and '] ' in message[:25]:
            message = message[message.index('] ')+2:]

        # Log at the appropriate level
        level = level.upper()
        if level == "DEBUG":
            logger.debug(message)
        elif level == "WARNING" or level == "WARN":
            logger.warning(message)
        elif level == "ERROR":
            logger.error(message)
        else:
            logger.info(message)

    def on_log_message_received(self, message, level):
        """Handle log messages from the logging system and display in UI"""
        if hasattr(self, 'log_widget') and self.log_widget:
            # Check if message should be filtered based on current filter setting
            if self.should_show_log(level):
                self.log_widget.add_log_message(message, level)

    def should_show_log(self, level):
        """Check if log message should be displayed based on current filter"""
        if not hasattr(self, 'log_level_filter'):
            return True

        filter_value = self.log_level_filter.currentText()

        if filter_value == "All":
            return True
        elif filter_value == "INFO+":
            return level in ["INFO", "WARNING", "ERROR"]
        elif filter_value == "WARNING+":
            return level in ["WARNING", "ERROR"]
        elif filter_value == "ERROR":
            return level == "ERROR"

        return True

    def apply_log_filter(self):
        """Reload all logs from file with current filter applied"""
        if not hasattr(self, 'log_widget'):
            return

        # Clear current display
        self.log_widget.clear_logs()

        # Re-read log file and apply filter
        try:
            log_file = get_log_file_path()
            if log_file.exists():
                with open(log_file, 'r', encoding='utf-8') as f:
                    # Read last 1000 lines
                    lines = f.readlines()[-1000:]
                    for line in lines:
                        # Parse line to extract level
                        # Format: [YYYY-MM-DD HH:MM:SS] [LEVEL] message
                        if '[' in line and ']' in line:
                            parts = line.split(']', 2)
                            if len(parts) >= 3:
                                level_part = parts[1].strip().strip('[')
                                if self.should_show_log(level_part):
                                    # Re-add with original formatting
                                    self.log_widget.add_log_message(line.rstrip('\n'), level_part)
        except Exception as e:
            self.log_widget.add_log_message(f"[{get_timestamp()}] [ERROR] Failed to reload logs: {e}", "ERROR")

    def copy_logs_to_clipboard(self):
        """Copy all visible logs to clipboard"""
        if not hasattr(self, 'log_widget'):
            return

        log_text = self.log_widget.get_all_text()
        if log_text:
            clipboard = QApplication.clipboard()
            clipboard.setText(log_text)

            # Show temporary message
            logger = get_logger()
            logger.info(f"Copied {len(log_text.splitlines())} log lines to clipboard")

    def clear_activity_log(self):
        """Clear the activity log display and truncate log file"""
        if not hasattr(self, 'log_widget'):
            return

        # Clear UI
        self.log_widget.clear_logs()

        # Truncate log file
        try:
            log_file = get_log_file_path()
            with open(log_file, 'w', encoding='utf-8') as f:
                f.write('')

            # Log the clear action
            logger = get_logger()
            logger.info("Activity log cleared by user")
        except Exception as e:
            logger = get_logger()
            logger.error(f"Failed to clear log file: {e}")

    def on_tab_changed(self, index):
        """Log when user switches tabs"""
        if not hasattr(self, 'main_tab_widget'):
            return

        tab_name = self.main_tab_widget.tabText(index)
        logger = get_logger()
        logger.debug(f"User switched to tab: {tab_name}")

    def on_exit(self):
        """Safely shut down the application and clean up resources"""
        # Prevent recursive calls
        if hasattr(self, '_is_exiting') and self._is_exiting:
            return
        self._is_exiting = True

        try:
            # Log exit attempt
            print(f"[{get_timestamp()}] Application exit initiated")

            # Send offline status before cleanup
            self.publish_offline_status()
            
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
            
            # Stop the analytics dashboard thread if it exists
            if hasattr(self, 'embedded_analytics') and self.embedded_analytics:
                try:
                    if hasattr(self.embedded_analytics, 'listener') and self.embedded_analytics.listener:
                        self.embedded_analytics.listener.stop()
                    if hasattr(self.embedded_analytics, 'listen_thread') and self.embedded_analytics.listen_thread:
                        self.embedded_analytics.listen_thread.quit()
                        if not self.embedded_analytics.listen_thread.wait(1000):
                            self.embedded_analytics.listen_thread.terminate()
                            self.embedded_analytics.listen_thread.wait(500)
                        self.embedded_analytics.listen_thread.deleteLater()
                        self.embedded_analytics.listen_thread = None
                        print(f"[{get_timestamp()}] Stopped analytics thread")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error stopping analytics thread: {e}")

            # Stop the TTS manager thread
            if hasattr(self, 'tts_manager') and self.tts_manager:
                try:
                    self.tts_manager.stop()
                    if not self.tts_manager.wait(2000):
                        self.tts_manager.terminate()
                        self.tts_manager.wait(500)
                    print(f"[{get_timestamp()}] Stopped TTS manager")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error stopping TTS manager: {e}")

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
                    # Wait with longer timeout and process events to allow clean shutdown
                    if not self.worker_thread.wait(2000):  # 2 second timeout
                        print(f"[{get_timestamp()}] Worker thread did not terminate cleanly, forcing termination")
                        self.worker_thread.terminate()
                        self.worker_thread.wait(500)  # Wait a bit after terminate
                    else:
                        print(f"[{get_timestamp()}] Worker thread stopped")
                    # Delete the thread object to ensure cleanup
                    self.worker_thread.deleteLater()
                    self.worker_thread = None
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
                    # Explicitly delete the tray icon to prevent segfault on macOS
                    self.tray_icon.deleteLater()
                    self.tray_icon = None
                    print(f"[{get_timestamp()}] Tray icon hidden")
                except Exception as e:
                    print(f"[{get_timestamp()}] Error hiding tray icon: {e}")

            print(f"[{get_timestamp()}] Application exit complete")
        except Exception as e:
            print(f"[{get_timestamp()}] Error during application exit: {e}")
        finally:
            # Mark application as quitting to allow window to close properly
            app = QApplication.instance()
            if app:
                app.setProperty("is_quitting", True)
                # Quit the application if we're not already in the process of quitting
                # This handles the case where user clicks Exit from menu
                # The Ctrl+C signal handler will have already called quit()
                if not app.property("quitting_from_signal"):
                    app.quit()
    
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

    def load_existing_redis_events(self):
        """Load all existing events from Redis at startup"""
        try:
            # Check if Redis worker exists and is connected
            if not hasattr(self, 'redis_worker') or not hasattr(self.redis_worker, 'redis_client') or self.redis_worker.redis_client is None:
                self.add_log(f"[{get_timestamp()}] Cannot load events from Redis: Redis not connected")
                return

            # Get all groups (both user's groups and all groups)
            all_groups = set()
            if self.redis_info:
                all_groups.update(self.redis_info.get('groups', []))
                all_groups.update(self.redis_info.get('all_groups', []))

            events_loaded = 0
            for group in all_groups:
                status_key = f"status:{group}"
                try:
                    # Get ALL events from the list (not just the first one)
                    # Redis lists are ordered newest first (index 0 = most recent)
                    event_count = self.redis_worker.redis_client.llen(status_key)
                    if event_count > 0:
                        # Load up to 20 most recent events (our display limit)
                        events_to_load = min(event_count, 20)
                        events = self.redis_worker.redis_client.lrange(status_key, 0, events_to_load - 1)

                        # Process events in reverse order (oldest first) so they appear in correct chronological order
                        for event_data in reversed(events):
                            try:
                                data = json.loads(event_data)
                                status = data.get('status')
                                if status:
                                    # Add event to history (update_group_status will filter out events without source)
                                    self.update_group_status(group, status, data)
                                    events_loaded += 1
                            except json.JSONDecodeError as e:
                                self.add_log(f"[{get_timestamp()}] Error parsing event from {group}: {e}")
                                continue
                except Exception as e:
                    self.add_log(f"[{get_timestamp()}] Error loading events from {status_key}: {e}")
                    continue

            if events_loaded > 0:
                self.add_log(f"[{get_timestamp()}] Loaded {events_loaded} existing events from Redis")
            else:
                self.add_log(f"[{get_timestamp()}] No existing events found in Redis")
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error loading events from Redis: {e}")

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

                # Load all existing events from Redis
                QTimer.singleShot(500, self.load_existing_redis_events)
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
        busylight_pop_url = ticket_info.get('busylight_pop_url', '')
        group = ticket_info.get('group', '')

        self.add_log(f"[{get_timestamp()}] Ticket #{ticket_id} received")

        if summary:
            self.add_log(f"[{get_timestamp()}] Summary: {summary}")
            # Handle text-to-speech if enabled
            self.speak_ticket_summary(summary)

        if busylight_pop_url:
            self.add_log(f"[{get_timestamp()}] URL to open: {busylight_pop_url}")
            # Handle URL opening if enabled and user belongs to the group
            if self.redis_info and group in self.redis_info.get('groups', []):
                self.open_ticket_url(busylight_pop_url)
            else:
                self.add_log(f"[{get_timestamp()}] URL popup skipped - user not a member of group '{group}'")
    
    def speak_ticket_summary(self, summary):
        """Speak the ticket summary using pyttsx3"""
        # Load TTS settings
        settings = QSettings("Busylight", "BusylightController")
        tts_enabled = settings.value("tts/enabled", False, type=bool)

        if not tts_enabled:
            return

        # Get TTS configuration
        slow = settings.value("tts/slow", False, type=bool)
        volume = settings.value("tts/volume", 0.9, type=float)
        voice_id = settings.value("tts/voice_id", None)

        # Add to TTS queue
        self.tts_manager.add_to_queue(summary, slow, volume, voice_id, "ticket summary")
        self.add_log(f"[{get_timestamp()}] Ticket summary added to TTS queue")
    
    def speak_group_status_event(self, group, status, data):
        """Speak group status events using pyttsx3"""
        # Skip TTS during app initialization to avoid speaking historical events
        if self.is_initializing:
            return

        # Load TTS settings
        settings = QSettings("Busylight", "BusylightController")
        tts_enabled = settings.value("tts/enabled", False, type=bool)

        if not tts_enabled:
            return

        # Create a human-readable message for the status event
        status_name = self.light_controller.COLOR_NAMES.get(status, status.title())
        source = data.get('source', 'Unknown')
        reason = data.get('reason', '')

        # Build the TTS message
        if reason:
            tts_message = f"Group {group} status changed to {status_name} by {source}. Reason: {reason}"
        else:
            tts_message = f"Group {group} status changed to {status_name} by {source}"

        # Get TTS configuration
        slow = settings.value("tts/slow", False, type=bool)
        volume = settings.value("tts/volume", 0.9, type=float)
        voice_id = settings.value("tts/voice_id", None)

        # Debug logging to see what's being spoken
        speed_str = "slow" if slow else "normal"
        self.add_log(f"[{get_timestamp()}] TTS Message: '{tts_message}' (length: {len(tts_message)})")
        self.add_log(f"[{get_timestamp()}] TTS Params - speed: {speed_str}, volume: {volume}, voice: {voice_id}")

        # Add to TTS queue
        self.tts_manager.add_to_queue(tts_message, slow, volume, voice_id, "group status event")
        self.add_log(f"[{get_timestamp()}] Group status event added to TTS queue")
    
    def open_ticket_url(self, url):
        """Open the ticket URL using a secure method"""
        # Skip URL opening during app initialization to avoid opening historical URLs
        if self.is_initializing:
            return

        # Load URL settings
        settings = QSettings("Busylight", "BusylightController")
        url_enabled = settings.value("url/enabled", False, type=bool)

        if not url_enabled:
            self.add_log(f"[{get_timestamp()}] URL opening is disabled in configuration")
            return

        # Prepend https:// if protocol is missing
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
            self.add_log(f"[{get_timestamp()}] Prepended https:// to URL: {url}")

        try:
            # Use the standard webbrowser module which is safer than shell commands
            if webbrowser.open(url):
                self.add_log(f"[{get_timestamp()}] Opening ticket URL safely using webbrowser module")
            else:
                self.add_log(f"[{get_timestamp()}] Failed to open URL with default browser")
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error opening URL: {e}")

    def update_group_status(self, group, status, data):
        """Handle group status updates for split panel layout"""
        # Store status data
        if not hasattr(self, 'group_event_history'):
            self.group_event_history = {}

        if group not in self.group_event_history:
            self.group_event_history[group] = []

        # Only add event to history if it has a real source (skip fake/default events)
        source = data.get('source', '')
        if source and source != 'unknown':
            # Check for duplicates - don't add if this exact event already exists
            event_timestamp = data.get('timestamp', '')
            is_duplicate = False

            for existing_event in self.group_event_history[group]:
                existing_data = existing_event.get('data', {})
                existing_timestamp = existing_data.get('timestamp', '')
                existing_source = existing_data.get('source', '')
                existing_status = existing_event.get('status', '')

                # Consider it a duplicate if timestamp, source, and status match
                if (existing_timestamp == event_timestamp and
                    existing_source == source and
                    existing_status == status):
                    is_duplicate = True
                    break

            # Only add if not a duplicate
            if not is_duplicate:
                self.group_event_history[group].append({
                    'status': status,
                    'timestamp': get_timestamp(),
                    'data': data
                })

                # Keep only last 20 events
                self.group_event_history[group] = self.group_event_history[group][-20:]

        self.group_statuses[group] = {
            'status': status,
            'timestamp': get_timestamp(),
            'data': data
        }

        # Trigger text-to-speech announcement only for groups the user is a member of
        if self.redis_info and group in self.redis_info.get('groups', []):
            self.speak_group_status_event(group, status, data)

        # Update colored dots in list items (both separate and combined panels)
        self.update_group_dot_color(group, status, 'my_groups')
        self.update_group_dot_color(group, status, 'all_groups')
        self.update_group_dot_color(group, status, 'combined_my')
        self.update_group_dot_color(group, status, 'combined_all')

        # Update detail panel if this group is currently selected
        if group in self.group_widgets:
            widgets = self.group_widgets[group]
            list_widget = widgets.get('list_widget')

            if list_widget and list_widget.currentItem():
                # Check if the current group is selected
                current_item = list_widget.currentItem()
                for key, value in self.list_item_to_group.items():
                    if value['item'] == current_item and value['group'] == group:
                        # Update the detail panel
                        self.update_detail_panel(group, widgets)
                        break

    def update_group_dot_color(self, group, status, panel_id):
        """Update the colored dot for a group in the specified panel"""
        key = f"{panel_id}_{group}"
        if hasattr(self, 'list_item_to_group') and key in self.list_item_to_group:
            dot_label = self.list_item_to_group[key]['dot_label']

            # Get status color
            if status in self.light_controller.COLOR_MAP:
                r, g, b = self.light_controller.COLOR_MAP[status]
                color = f"rgb({r}, {g}, {b})"
            else:
                color = "#00ff00"  # Default green

            dot_label.setStyleSheet(f"color: {color}; font-size: 16px;")

    def update_detail_panel(self, group, widgets):
        """Update the detail panel with current group information"""
        status_info = widgets.get('status_info')
        event_detail = widgets.get('event_detail')
        header_label = widgets.get('header_label')

        if not status_info or not event_detail:
            return

        # Get current status
        if group in self.group_statuses:
            status_data = self.group_statuses[group]
            status = status_data['status']
            timestamp = status_data['timestamp']
            status_name = self.light_controller.COLOR_NAMES.get(status, status.title())

            # Update header and status info
            if header_label:
                header_label.setText(f"Group: {group}")
            status_info.setText(f"Status: {status_name} | Last Update: {timestamp}")

        # Update event history - clear existing cards and add new ones
        # event_detail is now a QVBoxLayout, not a QTextEdit
        # Clear existing widgets
        while event_detail.count() > 1:  # Keep the stretch at the end
            item = event_detail.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # Get adaptive colors
        colors = get_adaptive_colors()

        # Add event cards
        if hasattr(self, 'group_event_history') and group in self.group_event_history and len(self.group_event_history[group]) > 0:
            # Sort events by timestamp (most recent first)
            sorted_events = sorted(
                self.group_event_history[group],
                key=lambda e: e.get('data', {}).get('timestamp', ''),
                reverse=True
            )

            # Add events in sorted order (most recent first)
            for event in sorted_events:
                event_card = self.create_event_card(event, colors)
                event_detail.insertWidget(event_detail.count() - 1, event_card)  # Insert before stretch
        else:
            # Show "no events" message
            no_events_label = QLabel("No events yet...")
            no_events_label.setStyleSheet(f"""
                color: {colors['text_secondary']};
                font-size: 13px;
                padding: 20px;
            """)
            no_events_label.setAlignment(Qt.AlignCenter)
            event_detail.insertWidget(0, no_events_label)

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

    def show_event_detail_dialog(self, event_data):
        """Show a popup dialog with full event details"""
        dialog = QDialog(self)
        dialog.setWindowTitle("Event Details")
        dialog.setModal(True)
        dialog.setMinimumWidth(700)
        dialog.resize(700, 500)

        colors = get_adaptive_colors()
        layout = QVBoxLayout(dialog)
        layout.setSpacing(16)
        layout.setContentsMargins(20, 20, 20, 20)

        # Parse event data
        data = event_data.get('data', {})
        status = event_data.get('status', 'normal')
        timestamp = data.get('timestamp', '')
        source = data.get('source', 'Unknown')
        reason = data.get('reason', '')
        ticket = data.get('ticket', '')
        summary = data.get('summary', '')
        url = data.get('busylight_pop_url', '')

        # Format timestamp
        if 'T' in timestamp and '.' in timestamp:
            timestamp = timestamp.split('.')[0].replace('T', ' ')

        # Get status color
        if status in self.light_controller.COLOR_MAP:
            r, g, b = self.light_controller.COLOR_MAP[status]
            status_color = f"rgb({r}, {g}, {b})"
        else:
            status_color = colors['accent_green']

        # Status badge
        status_label = QLabel(status.upper())
        status_label.setAlignment(Qt.AlignCenter)
        # Use black text for light colors (yellow), white for dark colors
        text_color = "black" if status in ['warning'] else "white"
        status_label.setStyleSheet(f"""
            background: {status_color};
            color: {text_color};
            padding: 8px 20px;
            border-radius: 15px;
            font-size: 14px;
            font-weight: bold;
        """)
        layout.addWidget(status_label)

        # Scroll area for content
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(f"""
            QScrollArea {{
                border: none;
                background: transparent;
            }}
        """)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setSpacing(12)
        content_layout.setContentsMargins(0, 0, 0, 0)

        # Add fields with labels and values in separate rows for better wrapping
        def add_field(label_text, value_text, is_link=False):
            # Label
            label = QLabel(label_text)
            label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 11px; font-weight: bold;")
            content_layout.addWidget(label)

            # Value
            if is_link:
                full_url = value_text if value_text.startswith('http') else f"https://{value_text}"
                value = QLabel(f'<a href="{full_url}" style="color: {colors["accent_blue"]};">{full_url}</a>')
                value.setOpenExternalLinks(True)
                value.setTextInteractionFlags(Qt.TextBrowserInteraction)
            else:
                value = QLabel(value_text)
                value.setTextInteractionFlags(Qt.TextSelectableByMouse)

            value.setWordWrap(True)
            value.setStyleSheet(f"""
                color: {colors['text_primary']};
                font-size: 13px;
                padding: 6px 10px;
                background: {colors['bg_secondary']};
                border-radius: 4px;
            """)
            content_layout.addWidget(value)

        # Add all fields
        add_field("Time", timestamp)
        add_field("Source", source)

        if reason:
            add_field("Reason", reason)

        if ticket:
            add_field("Ticket", ticket)

        if summary:
            add_field("Summary", summary)

        if url:
            add_field("URL", url, is_link=True)

        content_layout.addStretch()
        scroll_area.setWidget(content_widget)
        layout.addWidget(scroll_area)

        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: {colors['accent_blue']};
                color: white;
                border: none;
                padding: 10px 30px;
                border-radius: 6px;
                font-weight: 600;
                font-size: 13px;
            }}
            QPushButton:hover {{
                background: {colors['hover_bg']};
                color: {colors['text_primary']};
            }}
        """)
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignCenter)

        dialog.exec()

    def create_event_card(self, event_data, colors):
        """Create a clickable event card widget with compact styling"""
        card = QWidget()
        card.setObjectName("event_card")
        card.setCursor(Qt.PointingHandCursor)  # Show it's clickable

        # Get status color for the left border
        status = event_data.get('status', 'normal')
        if status in self.light_controller.COLOR_MAP:
            r, g, b = self.light_controller.COLOR_MAP[status]
            status_color = f"rgb({r}, {g}, {b})"
        else:
            status_color = colors['accent_green']

        card.setStyleSheet(f"""
            QWidget#event_card {{
                background: {colors['bg_secondary']};
                border-left: 4px solid {status_color};
                border-radius: 8px;
                padding: 10px;
                margin: 4px 0;
            }}
            QWidget#event_card:hover {{
                background: {colors['hover_bg']};
            }}
            QLabel {{
                background: transparent;
                border: none;
            }}
        """)

        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)
        card_layout.setContentsMargins(8, 6, 8, 6)

        # Parse event data
        data = event_data.get('data', {})
        timestamp = data.get('timestamp', '')
        source = data.get('source', 'Unknown')
        reason = data.get('reason', '')
        url = data.get('busylight_pop_url', '')

        # Format timestamp - show only time if it's today
        if 'T' in timestamp:
            time_part = timestamp.split('T')[1].split('.')[0] if '.' in timestamp else timestamp.split('T')[1]
            timestamp = time_part

        # Header row with timestamp and status
        header_layout = QHBoxLayout()

        timestamp_label = QLabel(timestamp)
        timestamp_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 11px;")
        header_layout.addWidget(timestamp_label)

        header_layout.addStretch()

        status_badge = QLabel(status.upper())
        # Use black text for yellow/warning, white for others
        badge_text_color = "black" if status in ['warning'] else "white"
        status_badge.setStyleSheet(f"""
            background: {status_color};
            color: {badge_text_color};
            padding: 2px 8px;
            border-radius: 8px;
            font-size: 9px;
            font-weight: bold;
        """)
        header_layout.addWidget(status_badge)

        card_layout.addLayout(header_layout)

        # Source
        source_label = QLabel(source)
        source_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; font-weight: 600;")
        card_layout.addWidget(source_label)

        # Reason - truncate if too long
        if reason:
            # Handle case where reason might be a list
            if isinstance(reason, list):
                reason = ', '.join(str(r) for r in reason) if reason else ''
            reason = str(reason)  # Ensure it's a string
            truncated_reason = reason if len(reason) <= 50 else reason[:47] + "..."
            reason_label = QLabel(truncated_reason)
            reason_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 11px;")
            card_layout.addWidget(reason_label)

        # URL indicator - just show if URL exists, don't display full URL
        if url:
            url_indicator = QLabel("🔗 Has link - click for details")
            url_indicator.setStyleSheet(f"color: {colors['accent_blue']}; font-size: 10px; font-style: italic;")
            card_layout.addWidget(url_indicator)

        # Make card clickable to show full details
        def on_card_click(event):
            self.show_event_detail_dialog(event_data)

        card.mousePressEvent = on_card_click

        return card

    def create_split_panel_layout(self, groups, colors, panel_id="panel"):
        """Create a split panel view - master-detail layout with colored status dots"""
        # Main splitter container
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName(panel_id)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {colors['border_secondary']};
                width: 2px;
            }}
            QSplitter::handle:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        # Left panel: List of groups
        list_widget = QListWidget()

        # Enable drag and drop for reordering
        list_widget.setDragDropMode(QListWidget.InternalMove)
        list_widget.setDefaultDropAction(Qt.MoveAction)

        list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {colors['bg_secondary']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 2px;
                margin: 1px 0;
                min-height: 32px;
            }}
            QListWidget::item:hover {{
                background: {colors['hover_bg']};
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: {colors['accent_blue']};
                border-radius: 6px;
            }}
        """)
        list_widget.setMinimumWidth(200)
        list_widget.setMaximumWidth(300)

        # Add groups to list with colored dots
        # Store mapping of list items to group names for updates
        if not hasattr(self, 'list_item_to_group'):
            self.list_item_to_group = {}

        # Sort groups by saved order
        sorted_groups = self.get_sorted_groups(groups, panel_id)

        for group in sorted_groups:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 36))  # Set proper height to avoid text cutoff

            # Create widget with colored dot
            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent;")  # Make seamless
            item_widget.setCursor(Qt.OpenHandCursor)  # Show drag cursor
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(4, 6, 8, 6)  # Reduced left margin for more space
            item_layout.setSpacing(6)  # Reduced spacing between elements

            # Drag handle icon (three horizontal lines)
            drag_handle = QLabel("☰")
            drag_handle.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px;")
            drag_handle.setAlignment(Qt.AlignLeft)  # Left-align the icon
            drag_handle.setFixedSize(14, 20)  # Slightly narrower
            drag_handle.setToolTip("Drag to reorder")
            item_layout.addWidget(drag_handle)

            # Status dot - bright green
            dot_label = QLabel("●")
            dot_label.setStyleSheet("color: #00ff00; font-size: 16px;")  # Bright green
            dot_label.setAlignment(Qt.AlignCenter)
            dot_label.setFixedSize(20, 20)
            item_layout.addWidget(dot_label)

            # Group name
            name_label = QLabel(group)
            name_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; background: transparent;")
            item_layout.addWidget(name_label, 1)  # Stretch to take remaining space

            list_widget.addItem(item)
            list_widget.setItemWidget(item, item_widget)

            # Store mapping for status updates
            self.list_item_to_group[f"{panel_id}_{group}"] = {
                'item': item,
                'list_widget': list_widget,
                'dot_label': dot_label,
                'group': group
            }

        # Right panel: Event history detail
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header_label = QLabel("Select a group to view details")
        header_label.setStyleSheet(f"""
            color: {colors['text_primary']};
            font-size: 16px;
            font-weight: bold;
            padding: 8px;
        """)
        detail_layout.addWidget(header_label)

        # Status info
        status_info = QLabel("")
        status_info.setStyleSheet(f"""
            color: {colors['text_secondary']};
            font-size: 13px;
            padding: 4px 8px;
        """)
        detail_layout.addWidget(status_info)

        # Event history - scrollable area with event cards
        event_scroll = QScrollArea()
        event_scroll.setWidgetResizable(True)
        event_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        event_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {colors['bg_primary']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
            }}
            QScrollBar:vertical {{
                background: {colors['bg_secondary']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {colors['border_secondary']};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        # Container for event cards
        event_container = QWidget()
        event_layout = QVBoxLayout(event_container)
        event_layout.setSpacing(8)
        event_layout.setContentsMargins(8, 8, 8, 8)
        event_layout.addStretch()  # Push cards to top

        event_scroll.setWidget(event_container)
        detail_layout.addWidget(event_scroll)

        # Store reference to event layout for updates
        event_detail = event_layout  # Keep same variable name for compatibility

        # Add panels to splitter
        splitter.addWidget(list_widget)
        splitter.addWidget(detail_container)
        splitter.setSizes([250, 750])  # 25% left, 75% right

        # Store references
        if not hasattr(self, 'group_widgets'):
            self.group_widgets = {}

        # Create entries for each group in split panel mode
        for group in groups:
            self.group_widgets[group] = {
                'mode': 'split_panel',
                'widget': splitter,
                'list_widget': list_widget,
                'header_label': header_label,
                'status_info': status_info,
                'event_detail': event_detail
            }

        # Handle selection changes
        def on_selection_changed():
            current_item = list_widget.currentItem()
            if current_item:
                # Find group name from stored mapping
                group_name = None
                for key, value in self.list_item_to_group.items():
                    if value['item'] == current_item and key.startswith(panel_id):
                        group_name = value['group']
                        break

                if group_name:
                    # Load stored data for the selected group
                    if group_name in self.group_widgets:
                        self.update_detail_panel(group_name, self.group_widgets[group_name])
                    else:
                        # Fallback if no data exists yet
                        header_label.setText(f"Group: {group_name}")
                        status_info.setText("Status: Normal | Last Update: Never")

                        # Clear event layout and show "no events" message
                        while event_detail.count() > 1:
                            item = event_detail.takeAt(0)
                            if item.widget():
                                item.widget().deleteLater()

                        colors = get_adaptive_colors()
                        no_events_label = QLabel("No events yet...")
                        no_events_label.setStyleSheet(f"""
                            color: {colors['text_secondary']};
                            font-size: 13px;
                            padding: 20px;
                        """)
                        no_events_label.setAlignment(Qt.AlignCenter)
                        event_detail.insertWidget(0, no_events_label)

        list_widget.currentItemChanged.connect(on_selection_changed)

        # Double-click handler to open update dialog (only for My Groups, not All Groups)
        def on_double_click(item):
            # Find which group was double-clicked
            group_name = None
            for key, value in self.list_item_to_group.items():
                if value['item'] == item and key.startswith(panel_id):
                    group_name = value['group']
                    break

            if group_name and panel_id == "my_groups":
                # Open group-specific update dialog
                dialog = GroupStatusUpdateDialog(group_name, self)
                dialog.exec()

        list_widget.itemDoubleClicked.connect(on_double_click)

        # Connect signal to save order when items are reordered
        def on_rows_moved():
            self.save_group_order(list_widget, panel_id)

        list_widget.model().rowsMoved.connect(on_rows_moved)

        # Select first item by default
        if list_widget.count() > 0:
            list_widget.setCurrentRow(0)

        return splitter

    def create_combined_groups_panel_layout(self, my_groups, other_groups, colors):
        """Create a combined split panel view for My Groups and All Groups with section headers"""
        # Main splitter container
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("combined_groups")
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {colors['border_secondary']};
                width: 2px;
            }}
            QSplitter::handle:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        # Left panel: List of groups with sections (using custom widget to prevent cross-section dragging)
        list_widget = SectionedListWidget()

        # Enable drag and drop for reordering
        list_widget.setDragDropMode(SectionedListWidget.InternalMove)
        list_widget.setDefaultDropAction(Qt.MoveAction)

        list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {colors['bg_secondary']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 2px;
                margin: 1px 0;
                min-height: 32px;
            }}
            QListWidget::item:hover {{
                background: {colors['hover_bg']};
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: {colors['accent_blue']};
                border-radius: 6px;
            }}
        """)
        list_widget.setMinimumWidth(200)
        list_widget.setMaximumWidth(300)

        # Store reference to list widget
        self.combined_groups_list_widget = list_widget

        # Store mapping of list items to group names for updates
        if not hasattr(self, 'list_item_to_group'):
            self.list_item_to_group = {}

        # Track section boundaries for drag constraints
        self.my_groups_section_start = 0
        self.my_groups_section_end = 0
        self.other_groups_section_start = 0
        self.other_groups_section_end = 0

        # Add "My Groups" section header
        my_groups_header = QListWidgetItem()
        my_groups_header.setSizeHint(QSize(0, 28))
        my_groups_header.setFlags(Qt.NoItemFlags)  # Non-selectable, non-draggable
        header_widget = QWidget()
        header_widget.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(8, 4, 8, 4)
        header_label = QLabel("— My Groups —")
        header_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px; font-weight: bold;")
        header_layout.addWidget(header_label)
        list_widget.addItem(my_groups_header)
        list_widget.setItemWidget(my_groups_header, header_widget)
        self.my_groups_section_start = 1  # First group item starts after header

        # Sort my groups by saved order
        sorted_my_groups = self.get_sorted_groups(my_groups, "my_groups")

        # Add my groups
        for group in sorted_my_groups:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 36))
            item.setData(Qt.UserRole, group)  # Store group name
            item.setData(Qt.UserRole + 1, "my_groups")  # Store section

            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent;")
            item_widget.setCursor(Qt.OpenHandCursor)
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(4, 6, 8, 6)
            item_layout.setSpacing(6)

            # Drag handle
            drag_handle = QLabel("☰")
            drag_handle.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px;")
            drag_handle.setAlignment(Qt.AlignLeft)
            drag_handle.setFixedSize(14, 20)
            drag_handle.setToolTip("Drag to reorder")
            item_layout.addWidget(drag_handle)

            # Status dot
            dot_label = QLabel("●")
            dot_label.setStyleSheet("color: #00ff00; font-size: 16px;")
            dot_label.setAlignment(Qt.AlignCenter)
            dot_label.setFixedSize(20, 20)
            item_layout.addWidget(dot_label)

            # Group name
            name_label = QLabel(group)
            name_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; background: transparent;")
            item_layout.addWidget(name_label, 1)

            list_widget.addItem(item)
            list_widget.setItemWidget(item, item_widget)

            # Store mapping for status updates
            self.list_item_to_group[f"combined_my_{group}"] = {
                'item': item,
                'list_widget': list_widget,
                'dot_label': dot_label,
                'group': group
            }

        self.my_groups_section_end = list_widget.count()

        # Add "All Groups" section header
        all_groups_header = QListWidgetItem()
        all_groups_header.setSizeHint(QSize(0, 28))
        all_groups_header.setFlags(Qt.NoItemFlags)  # Non-selectable, non-draggable
        all_header_widget = QWidget()
        all_header_widget.setStyleSheet("background: transparent;")
        all_header_layout = QHBoxLayout(all_header_widget)
        all_header_layout.setContentsMargins(8, 4, 8, 4)
        all_header_label = QLabel("— All Groups —")
        all_header_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px; font-weight: bold;")
        all_header_layout.addWidget(all_header_label)
        list_widget.addItem(all_groups_header)
        list_widget.setItemWidget(all_groups_header, all_header_widget)
        self.other_groups_section_start = list_widget.count()

        # Sort other groups by saved order
        sorted_other_groups = self.get_sorted_groups(other_groups, "all_groups")

        # Add other groups
        for group in sorted_other_groups:
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 36))
            item.setData(Qt.UserRole, group)  # Store group name
            item.setData(Qt.UserRole + 1, "all_groups")  # Store section

            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent;")
            item_widget.setCursor(Qt.OpenHandCursor)
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(4, 6, 8, 6)
            item_layout.setSpacing(6)

            # Drag handle
            drag_handle = QLabel("☰")
            drag_handle.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 12px;")
            drag_handle.setAlignment(Qt.AlignLeft)
            drag_handle.setFixedSize(14, 20)
            drag_handle.setToolTip("Drag to reorder")
            item_layout.addWidget(drag_handle)

            # Status dot
            dot_label = QLabel("●")
            dot_label.setStyleSheet("color: #00ff00; font-size: 16px;")
            dot_label.setAlignment(Qt.AlignCenter)
            dot_label.setFixedSize(20, 20)
            item_layout.addWidget(dot_label)

            # Group name
            name_label = QLabel(group)
            name_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; background: transparent;")
            item_layout.addWidget(name_label, 1)

            list_widget.addItem(item)
            list_widget.setItemWidget(item, item_widget)

            # Store mapping for status updates
            self.list_item_to_group[f"combined_all_{group}"] = {
                'item': item,
                'list_widget': list_widget,
                'dot_label': dot_label,
                'group': group
            }

        self.other_groups_section_end = list_widget.count()

        # Right panel: Event history detail (same as before)
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(12, 12, 12, 12)

        # Header
        combined_header_label = QLabel("Select a group to view details")
        combined_header_label.setStyleSheet(f"""
            color: {colors['text_primary']};
            font-size: 16px;
            font-weight: bold;
            padding: 8px;
        """)
        detail_layout.addWidget(combined_header_label)

        # Status info
        combined_status_info = QLabel("")
        combined_status_info.setStyleSheet(f"""
            color: {colors['text_secondary']};
            font-size: 13px;
            padding: 4px 8px;
        """)
        detail_layout.addWidget(combined_status_info)

        # Event history - scrollable area
        event_scroll = QScrollArea()
        event_scroll.setWidgetResizable(True)
        event_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        event_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {colors['bg_primary']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
            }}
            QScrollBar:vertical {{
                background: {colors['bg_secondary']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {colors['border_secondary']};
                border-radius: 5px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        # Container for event cards
        event_container = QWidget()
        combined_event_layout = QVBoxLayout(event_container)
        combined_event_layout.setSpacing(8)
        combined_event_layout.setContentsMargins(8, 8, 8, 8)
        combined_event_layout.addStretch()

        event_scroll.setWidget(event_container)
        detail_layout.addWidget(event_scroll)

        # Add panels to splitter
        splitter.addWidget(list_widget)
        splitter.addWidget(detail_container)
        splitter.setSizes([250, 750])

        # Store references for all groups
        all_groups = my_groups + other_groups
        if not hasattr(self, 'group_widgets'):
            self.group_widgets = {}

        for group in all_groups:
            self.group_widgets[group] = {
                'mode': 'split_panel',
                'widget': splitter,
                'list_widget': list_widget,
                'header_label': combined_header_label,
                'status_info': combined_status_info,
                'event_detail': combined_event_layout
            }

        # Handle selection changes
        def on_combined_selection_changed():
            current_item = list_widget.currentItem()
            if current_item:
                group_name = current_item.data(Qt.UserRole)
                if group_name and group_name in self.group_widgets:
                    self.update_detail_panel(group_name, self.group_widgets[group_name])
                elif group_name:
                    combined_header_label.setText(f"Group: {group_name}")
                    combined_status_info.setText("Status: Normal | Last Update: Never")
                    # Clear event layout
                    while combined_event_layout.count() > 1:
                        item = combined_event_layout.takeAt(0)
                        if item.widget():
                            item.widget().deleteLater()
                    no_events_label = QLabel("No events yet...")
                    no_events_label.setStyleSheet(f"color: {colors['text_secondary']}; font-size: 13px; padding: 20px;")
                    no_events_label.setAlignment(Qt.AlignCenter)
                    combined_event_layout.insertWidget(0, no_events_label)

        list_widget.currentItemChanged.connect(on_combined_selection_changed)

        # Double-click handler - only opens dialog for My Groups
        def on_combined_double_click(item):
            group_name = item.data(Qt.UserRole)
            section = item.data(Qt.UserRole + 1)
            if group_name and section == "my_groups":
                dialog = GroupStatusUpdateDialog(group_name, self)
                dialog.exec()

        list_widget.itemDoubleClicked.connect(on_combined_double_click)

        # Save order when items are reordered
        def on_combined_rows_moved():
            self.save_combined_group_order(list_widget)

        list_widget.model().rowsMoved.connect(on_combined_rows_moved)

        # Select first selectable item by default
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.flags() & Qt.ItemIsSelectable:
                list_widget.setCurrentRow(i)
                break

        return splitter

    def save_combined_group_order(self, list_widget):
        """Save the order of groups in the combined list, respecting sections"""
        my_groups_order = []
        all_groups_order = []

        for i in range(list_widget.count()):
            item = list_widget.item(i)
            group_name = item.data(Qt.UserRole)
            section = item.data(Qt.UserRole + 1)
            if group_name:
                if section == "my_groups":
                    my_groups_order.append(group_name)
                elif section == "all_groups":
                    all_groups_order.append(group_name)

        # Save to settings
        self.settings.setValue("group_order/my_groups", my_groups_order)
        self.settings.setValue("group_order/all_groups", all_groups_order)

    def create_users_split_panel_layout(self, colors):
        """Create a split panel view for users - display only with status dots"""
        # Main splitter container
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("users_panel")
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {colors['border_secondary']};
                width: 2px;
            }}
            QSplitter::handle:hover {{
                background: {colors['accent_blue']};
            }}
        """)

        # Left panel: List of users
        list_widget = QListWidget()
        list_widget.setStyleSheet(f"""
            QListWidget {{
                background: {colors['bg_secondary']};
                border: 1px solid {colors['border_secondary']};
                border-radius: 8px;
                padding: 4px;
                outline: none;
            }}
            QListWidget::item {{
                background: transparent;
                border: none;
                padding: 2px;
                margin: 1px 0;
                min-height: 32px;
            }}
            QListWidget::item:hover {{
                background: {colors['hover_bg']};
                border-radius: 6px;
            }}
            QListWidget::item:selected {{
                background: {colors['accent_blue']};
                border-radius: 6px;
            }}
        """)
        list_widget.setMinimumWidth(200)
        list_widget.setMaximumWidth(300)

        # Store reference to list widget for later updates
        self.users_list_widget = list_widget

        # Right panel: User detail
        detail_container = QWidget()
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setContentsMargins(12, 12, 12, 12)

        # Header
        header_label = QLabel("Select a user to view details")
        header_label.setStyleSheet(f"""
            color: {colors['text_primary']};
            font-size: 16px;
            font-weight: bold;
            padding: 8px;
        """)
        detail_layout.addWidget(header_label)

        # Status info
        status_info = QLabel("")
        status_info.setStyleSheet(f"""
            color: {colors['text_secondary']};
            font-size: 13px;
            padding: 4px 8px;
        """)
        detail_layout.addWidget(status_info)

        # Groups info
        groups_label = QLabel("")
        groups_label.setStyleSheet(f"""
            color: {colors['text_secondary']};
            font-size: 13px;
            padding: 4px 8px;
        """)
        groups_label.setWordWrap(True)
        detail_layout.addWidget(groups_label)

        # Add spacer
        detail_layout.addStretch()

        # Store references for updates
        self.users_header_label = header_label
        self.users_status_info = status_info
        self.users_groups_label = groups_label

        # Add panels to splitter
        splitter.addWidget(list_widget)
        splitter.addWidget(detail_container)
        splitter.setSizes([250, 750])  # 25% left, 75% right

        # Handle selection changes
        def on_user_selection_changed():
            current_item = list_widget.currentItem()
            if current_item:
                username = current_item.data(Qt.UserRole)
                if username:
                    self.update_users_detail_panel(username)

        list_widget.currentItemChanged.connect(on_user_selection_changed)

        # Populate with initial data if available
        self.populate_users_list()

        return splitter

    def populate_users_list(self):
        """Populate the users list widget with all users, grouped by status with headers"""
        if not hasattr(self, 'users_list_widget'):
            return

        colors = get_adaptive_colors()
        self.users_list_widget.clear()
        self.user_widgets = {}

        # Status priority for sorting (lower number = higher priority / shown first)
        status_priority = {
            USER_STATUS_AVAILABLE: 0,
            USER_STATUS_BUSY: 1,
            USER_STATUS_AWAY: 2,
            USER_STATUS_BREAK: 3,
            USER_STATUS_OFFLINE: 4
        }

        # Status display names for headers
        status_headers = {
            USER_STATUS_AVAILABLE: "Available",
            USER_STATUS_BUSY: "Busy",
            USER_STATUS_AWAY: "Away",
            USER_STATUS_BREAK: "Break",
            USER_STATUS_OFFLINE: "Offline"
        }

        # Sort users by status priority first, then alphabetically by display name
        def get_sort_key(user):
            username = user.get('username', '')
            status = self.user_statuses.get(username, {}).get('status', USER_STATUS_OFFLINE)
            priority = status_priority.get(status, 4)
            # Use display_name for sorting if available, otherwise username
            display_name = user.get('display_name', '') or username
            return (priority, display_name.lower())

        sorted_users = sorted(self.all_users, key=get_sort_key)

        # Track current status section to add headers
        current_section = None
        first_selectable_row = None

        for user in sorted_users:
            username = user.get('username', '')
            display_name = user.get('display_name', '') or username
            status = self.user_statuses.get(username, {}).get('status', USER_STATUS_OFFLINE)

            # Add section header if status changed
            if status != current_section:
                current_section = status
                header_text = status_headers.get(status, status.capitalize())
                status_color = USER_STATUS_COLORS.get(status, USER_STATUS_COLORS['offline'])

                # Create header item
                header_item = QListWidgetItem()
                header_item.setSizeHint(QSize(0, 28))
                header_item.setFlags(Qt.NoItemFlags)  # Make header non-selectable
                header_item.setData(Qt.UserRole, None)  # No username for headers

                header_widget = QWidget()
                header_widget.setStyleSheet(f"background: {colors['bg_tertiary']}; border-radius: 4px;")
                header_layout = QHBoxLayout(header_widget)
                header_layout.setContentsMargins(8, 4, 8, 4)

                header_label = QLabel(f"— {header_text} —")
                header_label.setStyleSheet(f"color: {status_color}; font-size: 11px; font-weight: bold; background: transparent;")
                header_label.setAlignment(Qt.AlignCenter)
                header_layout.addWidget(header_label)

                self.users_list_widget.addItem(header_item)
                self.users_list_widget.setItemWidget(header_item, header_widget)

            # Create user item
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 36))
            item.setData(Qt.UserRole, username)  # Store username for lookup

            # Track first selectable row
            if first_selectable_row is None:
                first_selectable_row = self.users_list_widget.count()

            # Create widget with colored dot
            item_widget = QWidget()
            item_widget.setStyleSheet("background: transparent;")
            item_layout = QHBoxLayout(item_widget)
            item_layout.setContentsMargins(16, 6, 8, 6)  # Extra left margin for indentation
            item_layout.setSpacing(8)

            # Status dot
            dot_label = QLabel("●")
            color = USER_STATUS_COLORS.get(status, USER_STATUS_COLORS['offline'])
            dot_label.setStyleSheet(f"color: {color}; font-size: 16px;")
            dot_label.setAlignment(Qt.AlignCenter)
            dot_label.setFixedSize(20, 20)
            item_layout.addWidget(dot_label)

            # Display name (full name if available, otherwise username)
            name_label = QLabel(display_name)
            name_label.setStyleSheet(f"color: {colors['text_primary']}; font-size: 13px; background: transparent;")
            item_layout.addWidget(name_label, 1)

            self.users_list_widget.addItem(item)
            self.users_list_widget.setItemWidget(item, item_widget)

            # Store mapping for status updates
            self.user_widgets[f"users_{username}"] = {
                'item': item,
                'dot_label': dot_label,
                'username': username,
                'display_name': display_name
            }

        # Select first selectable item by default (skip header)
        if first_selectable_row is not None:
            self.users_list_widget.setCurrentRow(first_selectable_row)

    def update_users_detail_panel(self, username):
        """Update the users detail panel with selected user info"""
        if not hasattr(self, 'users_header_label'):
            return

        colors = get_adaptive_colors()
        user_data = self.user_statuses.get(username, {})
        status = user_data.get('status', USER_STATUS_OFFLINE)
        groups = user_data.get('groups', [])
        last_update = user_data.get('last_update', 'Never')
        display_name = user_data.get('display_name', username)

        # Update header with display name (and username if different)
        if display_name != username:
            self.users_header_label.setText(f"User: {display_name} ({username})")
        else:
            self.users_header_label.setText(f"User: {username}")

        # Update status with colored indicator
        status_color = USER_STATUS_COLORS.get(status, USER_STATUS_COLORS['offline'])
        status_display = status.capitalize() if status else 'Offline'
        self.users_status_info.setText(f"Status: <span style='color: {status_color};'>●</span> {status_display} | Last Update: {last_update if last_update else 'Never'}")

        # Update groups
        if groups:
            groups_text = ", ".join(groups)
            self.users_groups_label.setText(f"Groups: {groups_text}")
        else:
            self.users_groups_label.setText("Groups: None")

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

    def fetch_users_from_api(self):
        """Fetch list of all users from API for presence status tracking"""
        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT
            }
            url = "https://busylight.signalwire.me/api/users"
            response = requests.get(
                url,
                headers=headers,
                auth=(self.username, self.password),
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.all_users = data.get('users', [])
                self.add_log(f"[{get_timestamp()}] Fetched {len(self.all_users)} users from API")
                # Initialize user statuses with current data from API
                for user in self.all_users:
                    username = user.get('username', '')
                    # Build display_name from first_name/last_name if available
                    # Handle None values from API
                    first_name = user.get('first_name') or ''
                    last_name = user.get('last_name') or ''
                    if first_name or last_name:
                        display_name = f"{first_name} {last_name}".strip()
                    else:
                        display_name = username
                    # Store display_name in user dict for sorting/display
                    user['display_name'] = display_name
                    self.add_log(f"[{get_timestamp()}] User {username}: first='{first_name}', last='{last_name}', display='{display_name}'")
                    self.user_statuses[username] = {
                        'status': user.get('status', USER_STATUS_OFFLINE),
                        'groups': user.get('groups', []),
                        'last_update': user.get('last_status_update', ''),
                        'display_name': display_name
                    }
                # Populate Users tab if it exists
                if hasattr(self, 'users_list_widget'):
                    self.populate_users_list()
            else:
                self.add_log(f"[{get_timestamp()}] Failed to fetch users: HTTP {response.status_code}")
                self.all_users = []
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error fetching users from API: {e}")
            self.all_users = []

    def update_user_status(self, username, status, data):
        """Handle user presence status updates from Redis (display only, no light control)"""
        # Update local cache
        if username not in self.user_statuses:
            self.user_statuses[username] = {}
        old_status = self.user_statuses[username].get('status', USER_STATUS_OFFLINE)
        self.user_statuses[username]['status'] = status
        self.user_statuses[username]['last_update'] = data.get('timestamp', get_timestamp())

        self.add_log(f"[{get_timestamp()}] User '{username}' status: {status}")

        # If this is the current user, update the My Status UI elements
        if username == self.username:
            self.current_user_status = status
            self.update_status_selector_ui(status)
            self.update_tray_status_menu(status)

        # Re-sort and repopulate the users list if status changed (to move user to correct section)
        if old_status != status and hasattr(self, 'users_list_widget'):
            # Remember currently selected user
            selected_username = None
            if self.users_list_widget.currentItem():
                selected_username = self.users_list_widget.currentItem().data(Qt.UserRole)

            # Repopulate list (which will re-sort)
            self.populate_users_list()

            # Restore selection
            if selected_username:
                for i in range(self.users_list_widget.count()):
                    item = self.users_list_widget.item(i)
                    if item and item.data(Qt.UserRole) == selected_username:
                        self.users_list_widget.setCurrentRow(i)
                        break
        else:
            # Just update the dot color if status didn't change
            self.update_user_dot_color(username, status)

        # Update detail panel if this user is selected
        if hasattr(self, 'users_list_widget') and self.users_list_widget.currentItem():
            current_key = f"users_{self.users_list_widget.currentItem().data(Qt.UserRole)}"
            if current_key == f"users_{username}":
                self.update_users_detail_panel(username)

    def update_user_dot_color(self, username, status):
        """Update the status dot color for a user in the Users tab"""
        key = f"users_{username}"
        if key in self.user_widgets:
            widget_info = self.user_widgets[key]
            dot_label = widget_info.get('dot_label')
            if dot_label:
                color = USER_STATUS_COLORS.get(status, USER_STATUS_COLORS['offline'])
                dot_label.setStyleSheet(f"color: {color}; font-size: 16px;")

    def on_user_status_combo_changed(self, index):
        """Handle user status combo box change"""
        if hasattr(self, 'user_status_combo'):
            status = self.user_status_combo.itemData(index)
            if status:
                self.set_my_status(status)

    def set_my_status(self, status):
        """Set the current user's presence status"""
        if status not in [USER_STATUS_AVAILABLE, USER_STATUS_BUSY, USER_STATUS_AWAY, USER_STATUS_BREAK]:
            self.add_log(f"[{get_timestamp()}] Invalid user status: {status}")
            return False

        self.current_user_status = status

        # Publish status to API
        success = self.publish_user_status(status)

        if success:
            # Update UI elements
            self.update_status_selector_ui(status)
            self.update_tray_status_menu(status)
            self.add_log(f"[{get_timestamp()}] User status changed to: {status}")
        else:
            self.add_log(f"[{get_timestamp()}] Failed to publish user status: {status}")

        return success

    def publish_user_status(self, status):
        """Publish user status to the backend API"""
        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT
            }
            url = "https://busylight.signalwire.me/api/user_status"
            payload = {'status': status}

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                auth=(self.username, self.password),
                timeout=10
            )

            if response.status_code == 200:
                self.add_log(f"[{get_timestamp()}] User status published successfully: {status}")
                return True
            else:
                self.add_log(f"[{get_timestamp()}] Failed to publish user status: HTTP {response.status_code}")
                return False
        except Exception as e:
            self.add_log(f"[{get_timestamp()}] Error publishing user status: {e}")
            return False

    def update_status_selector_ui(self, status):
        """Update the status selector combo box without triggering signals"""
        if hasattr(self, 'user_status_combo'):
            # Block signals to prevent recursive calls
            self.user_status_combo.blockSignals(True)
            for i in range(self.user_status_combo.count()):
                if self.user_status_combo.itemData(i) == status:
                    self.user_status_combo.setCurrentIndex(i)
                    break
            self.user_status_combo.blockSignals(False)

    def update_tray_status_menu(self, status):
        """Update the tray menu status checkmarks"""
        if hasattr(self, 'status_action_available'):
            self.status_action_available.setChecked(status == USER_STATUS_AVAILABLE)
        if hasattr(self, 'status_action_busy'):
            self.status_action_busy.setChecked(status == USER_STATUS_BUSY)
        if hasattr(self, 'status_action_away'):
            self.status_action_away.setChecked(status == USER_STATUS_AWAY)
        if hasattr(self, 'status_action_break'):
            self.status_action_break.setChecked(status == USER_STATUS_BREAK)

    def publish_offline_status(self):
        """Send offline status when application is closing"""
        try:
            # Quick synchronous call with short timeout
            headers = {
                "Content-Type": "application/json",
                "User-Agent": USER_AGENT
            }
            url = "https://busylight.signalwire.me/api/user_status"
            payload = {'status': USER_STATUS_OFFLINE}

            response = requests.post(
                url,
                json=payload,
                headers=headers,
                auth=(self.username, self.password),
                timeout=3  # Short timeout for exit
            )

            if response.status_code == 200:
                print(f"[{get_timestamp()}] Offline status sent successfully")
            else:
                print(f"[{get_timestamp()}] Failed to send offline status: HTTP {response.status_code}")
        except Exception as e:
            print(f"[{get_timestamp()}] Could not send offline status: {e}")

    def start_redis_worker(self):
        """Start the Redis worker thread"""
        if self.redis_info:
            # Fetch users list from API before starting worker
            self.fetch_users_from_api()

            # Create Redis worker thread with Redis info from login
            self.worker_thread = QThread()
            self.redis_worker = RedisWorker(redis_info=self.redis_info, username=self.username)

            # Set users list on worker so it can subscribe to user status channels
            self.redis_worker.set_users_list(self.all_users)

            self.redis_worker.moveToThread(self.worker_thread)
            self.redis_worker.status_updated.connect(self.light_controller.set_status)
            self.redis_worker.connection_status.connect(self.update_redis_connection_status)
            self.redis_worker.log_message.connect(self.add_log)
            self.redis_worker.ticket_received.connect(self.process_ticket_info)
            self.redis_worker.group_status_updated.connect(self.update_group_status)
            self.redis_worker.user_status_updated.connect(self.update_user_status)
            self.worker_thread.started.connect(self.redis_worker.run)
            self.worker_thread.start()

    def complete_initialization(self):
        """Complete initialization tasks after the UI is ready"""
        self.is_initializing = False
        self.add_log(f"[{get_timestamp()}] Initialization complete - TTS now active for new events")

        # Re-enable apply button and restore text after worker restart is complete
        if hasattr(self, 'apply_button'):
            self.apply_button.setText(APPLY_SETTINGS_BUTTON_TEXT)
            self.apply_button.setEnabled(True)

        # Set user status to Available on login
        self.set_my_status(USER_STATUS_AVAILABLE)
        self.add_log(f"[{get_timestamp()}] User status set to Available on login")

    def show_analytics_dashboard(self):
        """Switch to the analytics tab"""
        # Show the main window and switch to analytics tab
        self.show_and_raise()

        # Find the analytics tab index and switch to it
        for i in range(self.main_tab_widget.count()):
            if self.main_tab_widget.tabText(i) == "Analytics":
                self.main_tab_widget.setCurrentIndex(i)
                break
    
# Main application
def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep app running when window is closed

    # Set up signal handler for Ctrl+C
    def signal_handler(sig, frame):
        print(f"\n[{get_timestamp()}] Shutting down gracefully...")
        app.setProperty("quitting_from_signal", True)
        app.quit()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Allow Python to handle signals by setting up a timer
    # This ensures the Python interpreter can process the signal
    timer = QTimer()
    timer.start(500)  # Check for signals every 500ms
    timer.timeout.connect(lambda: None)  # No-op to allow signal processing
    
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

    # Set app_id/wm_class on Linux, no-op on Mac/Windows
    app.setDesktopFileName("com.busylight.controller")
    
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

    # Check if we should show the window on startup
    settings = QSettings("Busylight", "BusylightController")
    start_minimized = settings.value("app/start_minimized", False, type=bool)

    if not start_minimized:
        # Show the window if not starting minimized
        window.show_and_raise()
        print(f"[{get_timestamp()}] Window shown on startup (start_minimized={start_minimized})")
    else:
        # Start minimized to tray
        print(f"[{get_timestamp()}] Starting minimized to system tray (start_minimized={start_minimized})")

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
            # Explicitly delete the window to prevent segfault
            window.deleteLater()
    except Exception as e:
        print(f"Error during application cleanup: {e}")

    # Process all pending events multiple times to ensure cleanup completes
    for _ in range(5):
        QApplication.processEvents()
        time.sleep(0.05)

    # Final delay to allow Qt to finish cleanup
    time.sleep(0.1)

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
"""
D4Bot - Unified Control Panel
Single window for class selection, mode control, calibration, and monitoring.
"""
import sys
import os
from pathlib import Path
from threading import Thread, Lock
from time import sleep
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QStandardItemModel, QStandardItem, QFont
from PyQt5.QtWidgets import (QApplication, QComboBox, QPlainTextEdit, QMainWindow, QGridLayout,
                             QGroupBox, QPushButton, QHBoxLayout, QVBoxLayout, QLabel,
                             QStyleFactory, QWidget)

from helper import config_helper, logging_helper, process_helper
from bot import manager, rotation
from GUI import toolbox


# ═══════════════════════════════════════════════════════════════════
# Asset path resolution — works both dev and PyInstaller bundled
# ═══════════════════════════════════════════════════════════════════
def _get_asset_dir():
    """Get absolute path to assets/ directory."""
    if getattr(sys, 'frozen', False):
        # PyInstaller: assets are extracted to sys._MEIPASS
        return Path(sys._MEIPASS) / "assets"
    else:
        # Dev mode: relative to project root
        return Path(__file__).resolve().parents[2] / "assets"

ASSETS_DIR = _get_asset_dir()
ICON_PATH = str(ASSETS_DIR / 'layout' / 'mmorpg_helper.ico')
BG_PATH = str(ASSETS_DIR / 'layout' / 'mmorpg_helper_background.png')


# ═══════════════════════════════════════════════════════════════════
# Resolution-aware positioning
# Default designed for 1920×1080; auto-adjusts on larger screens
# ═══════════════════════════════════════════════════════════════════
def _get_screen_geometry():
    """Detect screen geometry for correct window placement."""
    try:
        app = QApplication.instance()
        if app is None:
            app_temp = QApplication(['dummy'])
            screen = app_temp.primaryScreen().availableGeometry()
            app_temp.quit()
        else:
            screen = app.primaryScreen().availableGeometry()
        return screen.width(), screen.height()
    except Exception:
        return 1920, 1080  # fallback

# Will be computed in __init__ when QApplication exists
WINDOW_WIDTH = 480
WINDOW_HEIGHT = 220


STYLE = """
QMainWindow {
    background-color: #1a1a2e;
}
QGroupBox {
    color: #e0a800;
    border: 1px solid #3a3a5e;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
    font-weight: bold;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
}
QPushButton {
    background-color: #2d2d44;
    color: white;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 6px 14px;
    font-weight: bold;
    min-width: 70px;
}
QPushButton:hover {
    background-color: #3d3d5e;
}
QPushButton#btnStart {
    background-color: #1a6b1a;
    color: white;
    font-size: 14px;
    padding: 8px 20px;
}
QPushButton#btnStart:hover {
    background-color: #228b22;
}
QPushButton#btnStart:disabled {
    background-color: #555;
    color: #999;
}
QPushButton#btnStop {
    background-color: #8b1a1a;
    color: white;
    font-size: 14px;
    padding: 8px 20px;
}
QPushButton#btnStop:hover {
    background-color: #aa2222;
}
QComboBox {
    background-color: #2d2d44;
    color: white;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 8px;
    min-width: 100px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #2d2d44;
    color: white;
    selection-background-color: #4a4a6e;
}
QPlainTextEdit {
    background-color: rgba(0,0,0,120);
    color: #aaa;
    border: 1px solid #3a3a5e;
    border-radius: 3px;
    font-family: Consolas, monospace;
    font-size: 11px;
}
QLabel#statusLabel {
    color: white;
    font-size: 13px;
    font-weight: bold;
    padding: 4px;
}
QLabel#statusRunning {
    color: #00ff00;
    font-size: 13px;
    font-weight: bold;
    padding: 4px;
}
QLabel#statusPaused {
    color: #ffaa00;
    font-size: 13px;
    font-weight: bold;
    padding: 4px;
}
QLabel#statusStopped {
    color: #ff4444;
    font-size: 13px;
    font-weight: bold;
    padding: 4px;
}
"""


class Overlay(QMainWindow):
    def __init__(self, parent=None):
        super(Overlay, self).__init__(parent)
        self.running = False
        self._lock = Lock()
        self.pause_req = False
        self._log_handler = None
        self.cfg = config_helper.read_config()
        self.name = self.cfg.get('apptitle', 'Diablo IV')
        self.proc = process_helper.ProcessHelper()
        self.robot = manager.Manager()

        # Resolution-aware positioning
        screen_w, screen_h = _get_screen_geometry()
        # Design for 1920×1080: window was at (1425, 825)
        # 2560×1440: place at right side, centered vertically
        if screen_w > 1920 or screen_h > 1080:
            # Scale position proportionally
            x = int(screen_w * 0.742)   # ~1900 on 2560
            y = int(screen_h * 0.573)   # ~825 on 1440
        else:
            x = 1425
            y = 825

        # Window setup
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        if os.path.exists(ICON_PATH):
            self.setWindowIcon(QIcon(ICON_PATH))
        QApplication.setStyle(QStyleFactory.create('Fusion'))
        self.setWindowTitle(self.name)
        self.setGeometry(x, y, WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setStyleSheet(STYLE)

        visible_window = QWidget(self)
        visible_window.setFixedSize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # === Build UI ===
        self.createClassSelector()
        self.createModeSelector()
        self.createControlButtons()
        self.createStatusArea()
        self.createLoggerConsole()

        mainLayout = QGridLayout()
        mainLayout.setSpacing(6)
        # Row 0: [Class Selector] [Mode Selector]
        mainLayout.addWidget(self.classGroup, 0, 0)
        mainLayout.addWidget(self.modeGroup, 0, 1)
        # Row 1: [Start/Stop Buttons + Status + Calibrate/Toolbox]
        mainLayout.addWidget(self.controlGroup, 1, 0, 1, 2)
        # Row 2: [Status Bar]
        mainLayout.addWidget(self.statusBar, 2, 0, 1, 2)
        # Row 3: [Log Console]
        mainLayout.addWidget(self.loggerConsole, 3, 0, 1, 2)
        mainLayout.setRowStretch(3, 1)
        mainLayout.setColumnStretch(0, 1)
        mainLayout.setColumnStretch(1, 1)

        self.setCentralWidget(visible_window)
        visible_window.setLayout(mainLayout)

        # Update status on startup
        self._update_status_ui()

        # Hotkey setup — keyboard module may fail, wrap safely
        self._setup_hotkeys()

    def _setup_hotkeys(self):
        """Set up global hotkeys. Safe fallback if keyboard module fails."""
        try:
            from keyboard import add_hotkey
            add_hotkey('end', lambda: self.on_press('exit'))
            add_hotkey('del', lambda: self.on_press('pause'))
            add_hotkey('capslock', lambda: self.on_press('pause'))
            logging_helper.log_info("Hotkeys registered: END=stop, DEL/CAPS=pause")
        except Exception as e:
            logging_helper.log_error(f"Hotkey registration failed: {e}")
            logging_helper.log_info("Hotkeys unavailable. Use GUI buttons to control.")

    # ── Class Selector ──────────────────────────────────────────────
    def update_class(self, idx):
        class_name = self.classCombo.currentText()
        logging_helper.log_info(f'Switched class to: {class_name}')
        config_helper.save_config('class', class_name)

    def createClassSelector(self):
        self.classGroup = QGroupBox("职业 Class")
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self.classCombo = QComboBox()
        self.classCombo.setMinimumWidth(120)
        classes = ['Barbarian', 'Druid', 'Spiritborn', 'Necromancer', 'Sorceress', 'Rogue', 'Paladin']
        self.classCombo.addItems(classes)

        # Set current class from config
        current_class = self.cfg.get('class', 'Barbarian')
        if current_class in classes:
            self.classCombo.setCurrentText(current_class)

        self.classCombo.currentTextChanged.connect(self.update_class)

        layout.addWidget(self.classCombo)
        self.classGroup.setLayout(layout)

    # ── Mode Selector ───────────────────────────────────────────────
    def update_mode(self, idx):
        mode = self.modeCombo.currentText()
        logging_helper.log_info(f'Switched mode to: {mode}')
        config_helper.save_config('mode', mode.lower())

    def createModeSelector(self):
        self.modeGroup = QGroupBox("模式 Mode")
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self.modeCombo = QComboBox()
        self.modeCombo.addItems(['Helltide', 'Nightmare Dungeon', 'Campaign'])

        current_mode = self.cfg.get('mode', 'helltide')
        mode_map = {'helltide': 'Helltide', 'nmd': 'Nightmare Dungeon', 'campaign': 'Campaign'}
        display_mode = mode_map.get(current_mode, 'Helltide')
        self.modeCombo.setCurrentText(display_mode)

        self.modeCombo.currentTextChanged.connect(self.update_mode)

        layout.addWidget(self.modeCombo)
        self.modeGroup.setLayout(layout)

    # ── Control Buttons ─────────────────────────────────────────────
    def createControlButtons(self):
        self.controlGroup = QGroupBox("控制 Control")
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)
        layout.setSpacing(8)

        # START button
        self.btnStart = QPushButton("▶ 开始挂机")
        self.btnStart.setObjectName("btnStart")
        self.btnStart.clicked.connect(self._start_bot)

        # STOP button
        self.btnStop = QPushButton("■ 停止")
        self.btnStop.setObjectName("btnStop")
        self.btnStop.clicked.connect(self._stop_bot)
        self.btnStop.setEnabled(False)

        # Calibrate button
        self.btnCalibrate = QPushButton("🎯 校准")
        self.btnCalibrate.clicked.connect(self._run_calibration)

        # Toolbox button
        self.btnToolbox = QPushButton("🔧 工具箱")
        self.btnToolbox.clicked.connect(self._open_toolbox)

        layout.addWidget(self.btnStart)
        layout.addWidget(self.btnStop)
        layout.addStretch(1)
        layout.addWidget(self.btnCalibrate)
        layout.addWidget(self.btnToolbox)
        self.controlGroup.setLayout(layout)

    # ── Status Area ─────────────────────────────────────────────────
    def createStatusArea(self):
        self.statusBar = QGroupBox("状态 Status")
        layout = QHBoxLayout()
        layout.setContentsMargins(5, 2, 5, 2)

        self.statusLabel = QLabel("● 已就绪 - 选择职业和模式后点击开始")
        self.statusLabel.setObjectName("statusLabel")
        self.statusLabel.setAlignment(Qt.AlignCenter)

        layout.addWidget(self.statusLabel)
        self.statusBar.setLayout(layout)

    # ── Logger Console ──────────────────────────────────────────────
    def createLoggerConsole(self):
        self.loggerConsole = QWidget()
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        handler = logging_helper.LogHandler(self)
        log_text_box = QPlainTextEdit(self)
        log_text_box.setMaximumBlockCount(500)
        log_text_box.setReadOnly(True)

        logging_helper.logger.addHandler(handler)
        handler.new_record.connect(log_text_box.appendPlainText)
        self._log_handler = handler

        layout.addWidget(log_text_box)
        self.loggerConsole.setLayout(layout)

    def closeEvent(self, event):
        self._stop_bot()
        root_logger = logging_helper.logger
        if self._log_handler:
            root_logger.removeHandler(self._log_handler)
            self._log_handler = None
        event.accept()

    # ── Actions ─────────────────────────────────────────────────────
    def _start_bot(self):
        """Start the bot rotation thread."""
        if not hasattr(self, 'rotation_thread') or not self.rotation_thread.is_alive():
            self.rotation_thread = Thread(target=self._rotation_loop, daemon=True)
            self.rotation_thread.start()
            self.btnStart.setEnabled(False)
            self.btnStop.setEnabled(True)
            self._update_status_ui()

    def _stop_bot(self):
        """Stop the bot rotation thread."""
        if self.running:
            self.running = False
        if hasattr(self, 'rotation_thread') and self.rotation_thread.is_alive():
            self.rotation_thread.join(timeout=2)
        self.btnStart.setEnabled(True)
        self.btnStop.setEnabled(False)
        self._update_status_ui()

    def _rotation_loop(self):
        """Main bot loop running in background thread."""
        logging_helper.log_info('🚀 D4Bot started')
        self.proc.set_foreground_window()
        self.running = True
        self._update_status_ui()

        while self.running:
            while self.should_pause():
                sleep(0.25)
            try:
                self.robot.game_manager()
            except Exception as ex:
                logging_helper.log_debug("game_manager error: %s" % ex)
                sleep(0.5)

        logging_helper.log_info("D4Bot stopped")
        self._update_status_ui()

    def _run_calibration(self):
        """Run coordinate calibration."""
        logging_helper.log_info("Starting calibration...")
        logging_helper.log_info("Make sure D4 is running at 1920x1080 windowed fullscreen")
        Thread(target=self._calibrate_thread, daemon=True).start()

    def _calibrate_thread(self):
        try:
            from bot.calibrate import run_calibration
            run_calibration()
            logging_helper.log_info("✅ Calibration complete! Coordinates saved.")
        except Exception as ex:
            logging_helper.log_error(f"❌ Calibration failed: {ex}")
            logging_helper.log_error("Check: D4 running? 1920x1080 windowed fullscreen? In-game?")

    def _open_toolbox(self):
        """Open the toolbox for skill icon capture."""
        app_toolbox = toolbox.Toolbox()
        app_toolbox.show()

    # ── Status UI ───────────────────────────────────────────────────
    def _update_status_ui(self):
        """Update status label and button states from main thread."""
        if self.running:
            if self.should_pause():
                self.statusLabel.setText("⏸ 已暂停 - 按 DEL 继续")
                self.statusLabel.setObjectName("statusPaused")
            else:
                cls = self.cfg.get('class', '?')
                mode = self.cfg.get('mode', '?')
                self.statusLabel.setText(f"▶ 运行中 | {cls} | {mode}")
                self.statusLabel.setObjectName("statusRunning")
        else:
            self.statusLabel.setText("● 已就绪 - 选择职业和模式后点击开始")
            self.statusLabel.setObjectName("statusStopped")

        # Re-apply stylesheet to refresh style
        self.statusLabel.style().unpolish(self.statusLabel)
        self.statusLabel.style().polish(self.statusLabel)

    # ── Hotkey actions ──────────────────────────────────────────────
    def on_press(self, key):
        if key == 'exit':
            logging_helper.log_info('_EXIT')
            self._stop_bot()
        elif key == 'pause':
            self.set_pause(not self.should_pause())
            if self.should_pause():
                logging_helper.log_info('_PAUSE')
            else:
                logging_helper.log_info('_RUN')
            self._update_status_ui()

    # ── Thread-safe pause ───────────────────────────────────────────
    def should_pause(self):
        with self._lock:
            return self.pause_req

    def set_pause(self, pause):
        with self._lock:
            self.pause_req = pause

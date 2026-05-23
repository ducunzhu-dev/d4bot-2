#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D4Bot Entry Point
==================
PRIORITY: Write a startup log BEFORE any imports that could crash silently.
This log is the ONLY way to diagnose "double-click EXE → nothing happens".
"""

import sys
import os
import traceback
from datetime import datetime
from pathlib import Path

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]

# ═══════════════════════════════════════════════════════════════════
# Phase 0: Startup log — WRITTEN BEFORE ANY DANGEROUS IMPORT
# This is the absolute first thing that runs. If anything below
# crashes, we'll at least know where.
# ═══════════════════════════════════════════════════════════════════
def _get_startup_log_path():
    """Get startup log path — works both dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        # PyInstaller bundled: log next to exe
        base = Path(sys.executable).parent
    else:
        # Dev mode: log in project root
        base = _ROOT
    log_dir = base / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "startup.log"

_STARTUP_LOG = _get_startup_log_path()

def _startup_log(msg: str):
    """Append a line to the startup log file."""
    try:
        with open(_STARTUP_LOG, 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except Exception:
        pass  # Can't log if we can't even write to disk

# Immediately log that we started
_startup_log("=== D4Bot startup ===")
_startup_log(f"Python: {sys.version}")
_startup_log(f"Executable: {sys.executable}")
_startup_log(f"Frozen: {getattr(sys, 'frozen', False)}")
_startup_log(f"Working dir: {os.getcwd()}")
_startup_log(f"Platform: {sys.platform}")

# ═══════════════════════════════════════════════════════════════════
# Phase 1: Safe imports with individual try/except
# Each failure is logged, so we know EXACTLY which module broke.
# ═══════════════════════════════════════════════════════════════════

# ---- PyQt5 (most likely to fail) ----
_startup_log("Importing PyQt5...")
try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import QCoreApplication, QTimer
    from PyQt5.QtGui import QFont
    _startup_log("PyQt5 OK")
except Exception as e:
    _startup_log(f"PyQt5 IMPORT FAILED: {e}")
    _startup_log(traceback.format_exc())
    # Can't show GUI without PyQt5, so we're done
    sys.exit(1)

# ---- signal (SIGINT only on POSIX!) ----
_startup_log("Importing signal module...")
import signal
_startup_log("signal module OK")

# ---- typing ----
from typing import Mapping
_startup_log("typing OK")

# ---- Project modules ----
_startup_log("Importing project modules...")
try:
    from helper import config_helper, logging_helper
    _startup_log("helper.config_helper, logging_helper OK")
except Exception as e:
    _startup_log(f"helper import FAILED: {e}")
    _startup_log(traceback.format_exc())
    sys.exit(2)

# ═══════════════════════════════════════════════════════════════════
# Phase 1.5: Initialize DPI-aware tolerance scaling
# MUST run before any pixel_matches_color call so 1440p/4K users
# get correct tolerance from the very first frame.
# ═══════════════════════════════════════════════════════════════════
_startup_log("Initializing DPI-aware tolerance scaling...")
try:
    from helper import image_helper
    from PIL import ImageGrab
    img = ImageGrab.grab()
    sw, sh = img.size
    dpi_ratio = max(sw / 1920.0, sh / 1080.0)
    if dpi_ratio > 1.8:
        image_helper.set_tolerance_scale(3.0)
    elif dpi_ratio > 1.2:
        image_helper.set_tolerance_scale(2.0)
    else:
        image_helper.set_tolerance_scale(1.0)
    _startup_log(f"Tolerance scale: {image_helper.get_tolerance_scale():.1f}x (screen: {sw}×{sh}, DPI ratio: {dpi_ratio:.2f})")
except Exception as e:
    _startup_log(f"Tolerance scaling init failed (non-fatal): {e}")

try:
    from GUI import overlay
    _startup_log("GUI.overlay imported OK")
except Exception as e:
    _startup_log(f"GUI.overlay import FAILED: {e}")
    _startup_log(traceback.format_exc())
    sys.exit(3)


APPNAME = 'notepad'
APPVERSION = '1.2026.0502.2312'


def main() -> int:
    """
    Entry point for the application.
    Initialisiert die GUI, liest Konfiguration und startet die QApplication-Schleife.
    Gibt einen Exit-Code zurueck (0 = OK, >0 = Fehler).
    """
    _startup_log("Entering main()")
    app = None
    try:
        cfg: Mapping = config_helper.read_config() or {}

        app_title = cfg.get('apptitle', APPNAME)
        app_class = cfg.get('class', 'unknown')

        _startup_log(f"Config loaded: apptitle={app_title}, class={app_class}")

        QCoreApplication.setApplicationName(app_title)
        QCoreApplication.setApplicationVersion(APPVERSION)

        app = QApplication(sys.argv)
        _startup_log("QApplication created OK")

        # Signal-Handler fuer sauberes Beenden bei STRG+C
        # FIX: SIGINT doesn't exist on Windows — only register on POSIX
        if hasattr(signal, 'SIGINT'):
            def _handle_sigint(sig, frame):
                logging_helper.log_info("Received interrupt signal, quitting...")
                QCoreApplication.quit()
            signal.signal(signal.SIGINT, _handle_sigint)
            _startup_log("SIGINT handler registered (POSIX)")
        else:
            _startup_log("SIGINT not available (Windows) — skipping handler")

        # Timer to keep signal handling responsive on some platforms
        timer = QTimer()
        timer.timeout.connect(lambda: None)
        timer.start(250)

        try:
            app_gui = overlay.Overlay()
            app_gui.show()
            _startup_log("Overlay GUI created and shown OK")
        except Exception as ex:
            _startup_log(f"Failed to initialize GUI overlay: {ex}")
            _startup_log(traceback.format_exc())
            logging_helper.log_error("Failed to initialize GUI overlay: %s" % ex)
            return 2

        logging_helper.log_info("====== %s %s ======" % (APPNAME, APPVERSION))
        logging_helper.log_info("Starting up bot engine...")
        logging_helper.log_info("Preset class %s is initialized" % app_class)
        _startup_log("Entering QApplication event loop")

        # Event loop starten und Exit-Code zurueckgeben
        exit_code = app.exec_()
        _startup_log(f"QApplication exited with code {exit_code}")
        return int(exit_code)

    except KeyboardInterrupt:
        logging_helper.log_info("Interrupted by user")
        _startup_log("KeyboardInterrupt")
        return 0
    except Exception as e:
        _startup_log(f"Unexpected exception: {e}")
        _startup_log(traceback.format_exc())
        logging_helper.log_error("Unexpected exception occurred: %s" % e)
        return 1
    finally:
        # Sicherstellen, dass QApplication beendet wird
        if app is not None:
            try:
                app.quit()
            except Exception:
                pass


if __name__ == '__main__':
    _startup_log("__main__ block entered, calling main()")
    try:
        exit_code = main()
        _startup_log(f"main() returned {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        _startup_log(f"CRASH in __main__: {e}")
        _startup_log(traceback.format_exc())
        sys.exit(99)

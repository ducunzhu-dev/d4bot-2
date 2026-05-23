from random import uniform
from time import sleep
from typing import Optional
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from pydirectinput import keyDown, keyUp, press, leftClick, rightClick

from helper import mouse_helper, image_helper, timer_helper, config_helper, logging_helper
from helper.timer_helper import TIMER_STOPPED

# Resolutions-Skalierung (alle Koordinaten sind 1920×1080 Design-Werte)
from helper.image_helper import scale_x, scale_y

# Skill-Assets relativ zum Projekt
SKILLPATH = _ROOT / "assets" / "skills"

# Timer-Instanzen für Abklingzeiten
timer1 = timer_helper.TimerHelper('timer1')
timer2 = timer_helper.TimerHelper('timer2')
timer3 = timer_helper.TimerHelper('timer3')

# Konfigurierbare Werte
MOVE_OFFSET_N = 25
POTION_TIMER_SEC = 3
EVADE_TIMER_SEC = 3
CLICK_DELAY_MIN = 0.11
CLICK_DELAY_MAX = 0.14


def press_combo(key: str) -> None:
    """
    Drückt eine Tastenkombination 'Shift' + key. Stellt sicher, dass Shift wieder losgelassen wird.
    """
    try:
        keyDown('shift')
        press(key)
    finally:
        try:
            keyUp('shift')
        except Exception:
            # KeyUp kann fehlschlagen, aber wir wollen nicht abstürzen
            pass


def rotation(x: Optional[int] = None, y: Optional[int] = None) -> None:
    """
    Setzt die Kampfrotation für eine spezifische Klasse basierend auf der Konfiguration.
    """
    try:
        cfg = config_helper.read_config() or {}
    except Exception as ex:
        logging_helper.log_error("Failed to read config for rotation: %s" % ex)
        return

    class_name = str(cfg.get('class', '')).strip().capitalize()
    valid = {'Druid', 'Spiritborn', 'Barbarian', 'Necromancer', 'Sorceress', 'Rogue', 'Warlock', 'Paladin'}

    if class_name in valid:
        combat_rotation(class_name.lower(), x, y)
    else:
        logging_helper.log_error("No viable class specified in configuration: %r" % class_name)


def combat_rotation(class_name: str, x: Optional[int], y: Optional[int]) -> None:
    """
    Führt die Kampfrotation aus: Health/Evade prüfen und Skills verwenden.
    """
    try:
        cfg = config_helper.read_config() or {}
    except Exception as ex:
        logging_helper.log_error("Failed to read config in combat_rotation: %s" % ex)
        return

    evade = cfg.get('evade', '')
    pot = cfg.get('pot', '')
    skill1 = cfg.get('skill1', '')
    skill2 = cfg.get('skill2', '')
    skill3 = cfg.get('skill3', '')
    skill4 = cfg.get('skill4', '')

    n = MOVE_OFFSET_N
    target_type = check_target_type(x, y, n)

    if target_type:
        handle_health_and_evade(evade, pot)
        use_skills(class_name, target_type, x, y, skill1, skill2, skill3, skill4)


def check_target_type(x: Optional[int], y: Optional[int], n: int) -> Optional[str]:
    """
    Determine if target is 'normal' or 'elite' using region sampling.
    Elite/Normal indicators appear at top of screen near enemy nameplate.
    V14: Replaced single-pixel checks with region sampling — works at all resolutions.
    """
    try:
        detect_mob = image_helper.detect_lines('mob') is not None
    except Exception as ex:
        logging_helper.log_debug("detect_lines error in check_target_type: %s" % ex)
        detect_mob = False

    if not detect_mob and x is None:
        return None

    try:
        w, h = image_helper._detect_screen_size()

        # Enemy nameplate area: top-center of screen
        nameplate_x = int(w * 0.35)
        nameplate_y = int(h * 0.02)
        nameplate_w = int(w * 0.30)
        nameplate_h = int(h * 0.06)

        has_red = image_helper.region_match(
            nameplate_x, nameplate_y, nameplate_w, nameplate_h,
            image_helper.is_reddish, min_pct=0.05, cols=8, rows=3)

        has_orange = image_helper.region_match(
            nameplate_x, nameplate_y, nameplate_w, nameplate_h,
            image_helper.is_orange, min_pct=0.03, cols=8, rows=3)

        has_purple = image_helper.region_match(
            nameplate_x, nameplate_y, nameplate_w, nameplate_h,
            image_helper.is_purple, min_pct=0.03, cols=8, rows=3)

        if detect_mob or has_red or has_orange:
            if x is not None and y is not None:
                mouse_helper.move_smooth(x + 400 + n, y + 50 + (n * 2), 1)
            # Elite: purple indicator
            if has_purple:
                if x is not None and y is not None:
                    mouse_helper.move_smooth(x + 400 + (n * 3), y + 50 + (n * 6), 1)
                return 'elite'
            return 'normal'
    except Exception as ex:
        logging_helper.log_debug("Error in check_target_type: %s" % ex)

    return None


def handle_health_and_evade(evade: str, pot: str) -> None:
    """
    Check health globe and use potion/evade if HP is low.
    V14: Replaced 3 hardcoded pixel checks with health globe region sampling.
    Samples the red health globe area — if red fill < 15% → low HP.
    """
    try:
        low_hp = _is_low_health()
        if low_hp:
            if locate_and_use_potion(pot):
                logging_helper.log_info('Used potion')
            if locate_and_use_evade(evade):
                logging_helper.log_info('Used evade')
    except Exception as ex:
        logging_helper.log_debug("handle_health_and_evade error: %s" % ex)


def _is_low_health() -> bool:
    """
    Check if health globe shows low HP using region sampling.
    The D4 health globe at bottom-left fills with red. When HP is low,
    most of the globe area is dark instead of red.
    """
    try:
        w, h = image_helper._detect_screen_size()

        # Health globe: bottom-left ~5-10% from left, bottom ~10% from bottom
        globe_x = int(w * 0.015)
        globe_y = int(h * 0.87)
        globe_w = int(w * 0.07)
        globe_h = int(h * 0.09)

        def is_health_red(r, g, b):
            """Bright red fill in health globe — indicates HP present."""
            s = r + g + b
            if s < 20:
                return False
            return r > 90 and r > g * 2.0 and r > b * 2.0

        # Sample health globe for red fill percentage.
        # Low HP: less than 15% of globe area shows red (most is dark/empty).
        samples = image_helper.sample_region(globe_x, globe_y, globe_w, globe_h, 6, 4)
        if not samples:
            return False
        red_count = sum(1 for r, g, b in samples if is_health_red(r, g, b))
        red_pct_actual = red_count / len(samples)

        # Low HP: less than 15% of globe area shows red
        return red_pct_actual < 0.15
    except Exception as ex:
        logging_helper.log_debug("_is_low_health error: %s" % ex)
        return False


def locate_and_use_potion(pot: str) -> bool:
    """
    Sucht nach Trank-Icons und benutzt den angegebenen Taste für Potion.
    """
    potion_images = ['pot.png']
    try:
        for img in potion_images:
            path = str(SKILLPATH / img)
            try:
                found = image_helper.locate_needle(path, conf=0.7)
            except Exception as ex:
                logging_helper.log_debug("locate_needle error for %s: %s" % (path, ex))
                found = False

            if found and timer1.get_timer_state() == TIMER_STOPPED:
                timer1.start_timer(POTION_TIMER_SEC)
                try:
                    press(pot)
                except Exception as ex:
                    logging_helper.log_debug("press(pot) failed: %s" % ex)
                sleep(uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
                return True
    except Exception as ex:
        logging_helper.log_debug("locate_and_use_potion error: %s" % ex)

    return False


def locate_and_use_evade(evade: str) -> bool:
    """
    Sucht nach Evade-Icon und führt Evade-Taste aus (mit Timer).
    """
    try:
        path = str(SKILLPATH / 'evade.png')
        try:
            found = image_helper.locate_needle(path, conf=0.7)
        except Exception as ex:
            logging_helper.log_debug("locate_needle error for evade: %s" % ex)
            found = False

        if found and timer2.get_timer_state() == TIMER_STOPPED:
            timer2.start_timer(EVADE_TIMER_SEC)
            try:
                press(evade)
            except Exception as ex:
                logging_helper.log_debug("press(evade) failed: %s" % ex)
            sleep(uniform(CLICK_DELAY_MIN, CLICK_DELAY_MAX))
            return True
    except Exception as ex:
        logging_helper.log_debug("locate_and_use_evade error: %s" % ex)

    return False


def use_skills(class_name: str, target_type: str, x: Optional[int], y: Optional[int],
               skill1: str, skill2: str, skill3: str, skill4: str) -> None:
    """
    Verwendet die Klassenskills basierend auf Skill-Icons und Ziel-Typ.
    Reihenfolge der Prüfungen bleibt wie bisher, Logging erweitert.
    """
    try:
        # Standardisierte Pfade für Skill-Icons
        def skill_icon(idx: str) -> str:
            return str(SKILLPATH / class_name / (idx + '.png'))

        if image_helper.locate_needle(skill_icon('04'), conf=0.6):
            press(skill4)
            logging_helper.log_info('Used skill 4')
        elif image_helper.locate_needle(skill_icon('03'), conf=0.6):
            press(skill3)
            logging_helper.log_info('Used skill 3')
        elif image_helper.locate_needle(skill_icon('01'), conf=0.6):
            press(skill1)
            logging_helper.log_info('Used skill 1')
        elif image_helper.locate_needle(skill_icon('02'), conf=0.6):
            press(skill2)
            logging_helper.log_info('Used skill 2')

        sleep(uniform(0.21, 0.24))

        if image_helper.locate_needle(skill_icon('05'), conf=0.9):
            rightClick()
            logging_helper.log_info('Used right mouse skill')
        elif x is not None and y is not None:
            leftClick()
            logging_helper.log_info('Used left mouse skill')

        sleep(uniform(0.21, 0.24))
    except Exception as ex:
        logging_helper.log_debug("use_skills error: %s" % ex)

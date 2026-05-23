import os
from typing import Tuple, Optional, Any
import pyautogui
import numpy as np
import cv2
from PIL import ImageGrab
from math import sqrt

from helper import mouse_helper, logging_helper

# ═══════════════════════════════════════════════════════════════════
# Resolution scaling — all hardcoded coords are designed for 1920×1080
# Automatically scaled to actual screen resolution
# ═══════════════════════════════════════════════════════════════════
_DESIGN_WIDTH = 1920
_DESIGN_HEIGHT = 1080
_screen_w = None
_screen_h = None

# ═══════════════════════════════════════════════════════════════════
# DPI-aware tolerance scaling — pixel color matching needs higher
# tolerance at higher resolutions because D4 renders with different
# antialiasing / color interpolation at 1440p vs 1080p.
# At 1440p, a pixel that matches within tolerance=30 at 1080p may
# have RGB values deviating 50-60+ from the expected values.
# ═══════════════════════════════════════════════════════════════════
_tolerance_scale = 1.0  # Multiplier applied to all pixel tolerances


def set_tolerance_scale(factor: float) -> None:
    """
    Set global tolerance multiplier for pixel matching.
    Higher DPI = higher tolerance needed.
    Call during startup/calibration based on detected resolution.

    Recommended values:
      1920×1080: 1.0 (default)
      2560×1440: 2.0 (double tolerance — antialiasing is different)
      3840×2160: 3.0
    """
    global _tolerance_scale
    _tolerance_scale = max(1.0, float(factor))
    logging_helper.log_info(
        f"Tolerance scale set to {_tolerance_scale:.1f}x "
        f"(resolution: {_screen_w or '?'}×{_screen_h or '?'})"
    )


def get_tolerance_scale() -> float:
    """Get current tolerance multiplier."""
    return _tolerance_scale


def scale_tolerance(d: int) -> int:
    """
    Scale a tolerance value by the DPI-aware factor.
    Use in all pixel matching calls to auto-adapt to 1440p/4K.
    """
    return int(d * _tolerance_scale)


def _detect_screen_size():
    """Detect primary monitor resolution. Cached after first call."""
    global _screen_w, _screen_h
    if _screen_w is not None:
        return _screen_w, _screen_h
    try:
        import tkinter
        root = tkinter.Tk()
        _screen_w = root.winfo_screenwidth()
        _screen_h = root.winfo_screenheight()
        root.destroy()
    except Exception:
        try:
            from PIL import ImageGrab
            img = ImageGrab.grab()
            _screen_w, _screen_h = img.size
        except Exception:
            _screen_w, _screen_h = _DESIGN_WIDTH, _DESIGN_HEIGHT
    return _screen_w, _screen_h


def scale_x(design_x: int) -> int:
    """Scale an X coordinate from 1920 design to current resolution."""
    w, _ = _detect_screen_size()
    return int(design_x * w / _DESIGN_WIDTH)


def scale_y(design_y: int) -> int:
    """Scale a Y coordinate from 1080 design to current resolution."""
    _, h = _detect_screen_size()
    return int(design_y * h / _DESIGN_HEIGHT)


def scale_region(design_region: tuple) -> tuple:
    """Scale a (left, top, width, height) region to current resolution."""
    left, top, w, h = design_region
    return (scale_x(left), scale_y(top), scale_x(left + w) - scale_x(left), scale_y(top + h) - scale_y(top))


def get_pixel_color_at_cursor() -> Tuple[int, int, int, int, int]:
    """
    Get the color of the pixel under the cursor.
    Returns:
        tuple: (x, y, r, g, b) - Cursor coordinates and pixel color.
    """
    try:
        x, y = mouse_helper.position()
        r, g, b = pyautogui.screenshot().getpixel((x, y))
        return x, y, r, g, b
    except Exception as ex:
        logging_helper.log_debug(f"get_pixel_color_at_cursor failed: {ex}")
        return -1, -1, -1, -1, -1


def get_pixel_color_at_coords(x: int, y: int) -> Tuple[int, int, int]:
    """
    Get the color of the pixel at coordinates.
    Returns:
        tuple: (r, g, b) - Pixel color.
    """
    try:
        r, g, b = pyautogui.screenshot().getpixel((int(x), int(y)))
        return r, g, b
    except Exception as ex:
        logging_helper.log_debug(f"get_pixel_color_at_coords({x},{y}) failed: {ex}")
        return -1, -1, -1


def save_image(region: Tuple[int, int, int, int], name: str, path: str) -> None:
    """
    Save a screenshot of a specific region to a file.
    Parameters:
        region (tuple): (left, top, width, height) - The region to capture.
        name (str): Name of the saved file (without extension).
        path (str): Directory where the file will be saved.
    """
    try:
        os.makedirs(path, exist_ok=True)
        img = pyautogui.screenshot(region=region)
        filepath = os.path.join(path, f"{name}.png")
        img.save(filepath)
        logging_helper.log_debug(f"Saved image {filepath}")
    except Exception as ex:
        logging_helper.log_debug(f"save_image failed for {name} @ {path}: {ex}")


def get_image_at_cursor(ix: int = 10, iy: int = 10, name: str = 'default', path: str = './assets/skills/') -> Tuple[int, int]:
    """
    Capture an image centered around the cursor position.
    Returns cursor coordinates.
    """
    x, y = mouse_helper.position()
    save_image((x, y, ix, iy), name, path)
    return x, y


def get_image_from_coordinates(x: int, y: int, name: str = 'default', path: str = './assets/skills/') -> Tuple[int, int]:
    """
    Backward-compatible wrapper for the toolbox API.
    """
    return get_image_at_coords(x, y, name=name, path=path)


def get_image_at_coords(x: int, y: int, ix: int = 10, iy: int = 10, name: str = 'default', path: str = './assets/skills/') -> Tuple[int, int]:
    """
    Capture an image at specified coordinates (centered on x,y).
    Returns the provided coordinates.
    """
    save_image((x, y, ix, iy), name, path)
    return x, y


def pixel_matches_color(x: int, y: int, exR: int, exG: int, exB: int, tolerance: int = 25) -> bool:
    """
    Check if a pixel matches the expected RGB color within a tolerance.
    Uses PIL ImageGrab (same coordinate system as calibrator) to avoid
    DPI-scaling mismatch that affects pyautogui on 1440p+ displays.

    Tolerance is automatically scaled by the DPI-aware factor — at 1440p
    the effective tolerance doubles to account for different rendering.
    """
    try:
        from PIL import ImageGrab
        r, g, b = ImageGrab.grab().getpixel((int(x), int(y)))
        effective_tol = int(tolerance * _tolerance_scale)
        return all(abs(int(actual) - int(expected)) <= effective_tol
                   for actual, expected in zip((r, g, b), (exR, exG, exB)))
    except Exception as ex:
        logging_helper.log_debug(f"pixel_matches_color({x},{y}) failed: {ex}")
        return False

    
def detect_lines(line_type: str = 'path') -> Optional[Tuple[int, int, int, int]]:
    """
    Detect narrow, curved lines of a given type ('path' or 'mob') by specified RGB color on the screen.
    Returns absolute bounding box (x, y, w, h) of the closest matching contour or None.
    """
    # RGB color ranges for different line types — regions scale with resolution
    line_config = {
        'path': {
            'lower': np.array([254, 254, 254], dtype=np.uint8),
            'upper': np.array([255, 255, 255], dtype=np.uint8),
            'screen_box': scale_region((600, 100, 800, 800))  # left, top, width, height
        },
        'mob': {
            'lower': np.array([155, 37, 1], dtype=np.uint8),
            'upper': np.array([168, 38, 1], dtype=np.uint8),
            'screen_box': scale_region((600, 100, 800, 800))  # left, top, width, height
        }
    }

    if line_type not in line_config:
        logging_helper.log_debug(f"detect_lines: unknown line_type '{line_type}'")
        return None

    cfg = line_config[line_type]
    left, top, screen_w, screen_h = cfg['screen_box']
    # PIL ImageGrab.grab(bbox) expects (left, top, right, bottom), not (left, top, width, height)
    right, bottom = left + screen_w, top + screen_h

    try:
        # Grab region and convert to RGB for processing
        img = ImageGrab.grab(bbox=(left, top, right, bottom))
        np_img = np.array(img)
        rgb = cv2.cvtColor(np_img, cv2.COLOR_BGR2RGB)
        mask = cv2.inRange(rgb, cfg['lower'], cfg['upper'])
        edges = cv2.Canny(mask, 50, 150)

        # findContours: robust gegen verschiedene cv2-Versionen
        contours_info = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours_info[0] if len(contours_info) == 2 else contours_info[1]

        screen_center_x = left + (screen_w // 2)
        screen_center_y = top + (screen_h // 2)
        min_distance = float('inf')
        closest_contour: Optional[Tuple[int, int, int, int]] = None

        for contour in contours:
            #if cv2.contourArea(contour) < 20:
            #    continue  # Rauschen �berspringen

            epsilon = 0.01 * cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, epsilon, True)
            x, y, w, h = cv2.boundingRect(contour)

            # Kontur-Koordinaten ins absolute Koordinatensystem umrechnen
            abs_x = left + x
            abs_y = top + y
            contour_center_x = abs_x + (w // 2)
            contour_center_y = abs_y + (h // 2)
            distance = sqrt((contour_center_x - screen_center_x) ** 2 + (contour_center_y - screen_center_y) ** 2)

            if line_type in ('path'):
                # Pfad ist typischerweise kurvig; wir erlauben kleine Konturen mit mehreren Punkten
                if len(approx) > 2 and distance < min_distance:
                    min_distance = distance
                    closest_contour = (abs_x, abs_y, w, h)
                    #cv2.imwrite(f"debug_{line_type}_hsv.png", rgb)  # Debug: save rgb image
                    #cv2.imwrite(f"debug_{line_type}_edges.png", edges)  # Debug: save edge image
                    logging_helper.log_debug(f"Detected curved line ('path') bbox {(abs_x, abs_y, w, h)}")
            elif line_type == 'mob':
                # Mob-Linien sind oft sehr schmal und lang; Filter nach minimaler Breite/H�he
                if w >= 20 and 1 <= h <= 6 and distance < min_distance:
                    min_distance = distance
                    closest_contour = (abs_x, abs_y, w, h)
                    #cv2.imwrite(f"debug_{line_type}_hsv.png", rgb)  # Debug: save rgb image
                    #cv2.imwrite(f"debug_{line_type}_edges.png", edges)  # Debug: save edge image
                    logging_helper.log_debug(f"Detected straight line ('mob') bbox {(abs_x, abs_y, w, h)}")

        if closest_contour:
            logging_helper.log_info(f"Closest contour to center: {closest_contour}")
            return closest_contour

    except Exception as ex:
        logging_helper.log_debug(f"detect_lines failed for type '{line_type}': {ex}")

    return None


def locate_needle(
    needle: str,
    haystack: Optional[str] = None,
    conf: float = 0.7,
    loctype: str = 'l',
    grayscale: bool = True,
    region: Tuple[int, int, int, int] = (525, 875, 1380, 1050)
) -> Any:
    """
    Searches the haystack image or the screen for the needle image.

    Returns:
        - If haystack is given: pyautogui.locate(...) result or (-1, -1) if not found.
        - If loctype == 'l': bool (found / not found).
        - If loctype == 'c': (x, y) center coordinates or (-1, -1) if not found.
    """
    def log_result(found: bool, context: str, result: Any = None) -> None:
        if found:
            logging_helper.log_debug(f"Found {context}: {needle} -> {result}")
        else:
            logging_helper.log_debug(f"Cannot find {context}: {needle}, conf={conf}, result={result}")

    try:
        if haystack:
            res = pyautogui.locate(needle, haystack, confidence=conf)
            if res:
                log_result(True, "needle in haystack", res)
                return res
            log_result(False, "needle in haystack")
            return (-1, -1)

        if loctype == 'l':
            res = pyautogui.locateOnScreen(needle, confidence=conf, region=region, grayscale=grayscale)
            if res:
                log_result(True, "'l' image", res)
                return True
            log_result(False, "'l' image")
            return False

        if loctype == 'c':
            res = pyautogui.locateCenterOnScreen(needle, confidence=conf, region=region, grayscale=grayscale)
            if res:
                coords = (int(res.x), int(res.y)) if hasattr(res, 'x') else (int(res[0]), int(res[1]))
                log_result(True, "'c' image", coords)
                return coords
            log_result(False, "'c' image")
            return (-1, -1)

    except Exception as ex:
        logging_helper.log_debug(f"locate_needle error for {needle}: {ex}")
        if loctype == 'c' or haystack:
            return (-1, -1)
        return False

    raise ValueError(f"Invalid loctype '{loctype}'. Must be 'l' or 'c'.")

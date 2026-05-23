"""
校准数据加载器 — 所有模块通过此接口获取坐标
优先级：用户校准 > 预制校准(按分辨率) > bundled默认 > 空
支持：1920×1080 / 2560×1440 预制校准文件
"""
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from typing import Dict, Any, Optional
import yaml

# 优先级：writable (EXE旁边) >  预制按分辨率 > bundled (MEIPASS)
if getattr(sys, "frozen", False):
    _WRITABLE_CALIB = Path(sys.executable).parent / "config" / "calibration.yaml"
else:
    _WRITABLE_CALIB = _ROOT / "config" / "calibration.yaml"
_BUNDLED_CALIB = _ROOT / "config" / "calibration.yaml"

# 预制校准文件映射 (分辨率 → 文件路径)
_PREBUILT_MAP = {
    (2560, 1440): _ROOT / "config" / "calibration_1440p.yaml",
    (1920, 1080): None,  # 1080p用自动校准，不需要预制
}

_cal_cache = None  # 单例缓存


def _detect_resolution():
    """检测当前屏幕分辨率"""
    try:
        from PIL import ImageGrab
        img = ImageGrab.grab()
        return img.size
    except Exception:
        return (1920, 1080)


def load_calibration() -> Dict:
    """
    加载校准数据（带缓存）
    优先级：用户 recali brated > 预制按分辨率 > bundled默认
    """
    global _cal_cache
    if _cal_cache is not None:
        return _cal_cache

    # 1. 用户手动校准过（writable location）
    if _WRITABLE_CALIB.exists():
        try:
            with open(_WRITABLE_CALIB, 'r', encoding='utf-8') as f:
                _cal_cache = yaml.safe_load(f) or {}
            if _cal_cache:
                return _cal_cache
        except Exception:
            pass

    # 2. 预制校准（按当前分辨率匹配）
    try:
        resolution = _detect_resolution()
        prebuilt_path = _PREBUILT_MAP.get(resolution)
        if prebuilt_path and prebuilt_path.exists():
            with open(prebuilt_path, 'r', encoding='utf-8') as f:
                _cal_cache = yaml.safe_load(f) or {}
            if _cal_cache:
                # 自动设置容差倍数
                _auto_set_tolerance(resolution)
                return _cal_cache
    except Exception:
        pass

    # 3. Bundled 默认校准
    if _BUNDLED_CALIB.exists():
        try:
            with open(_BUNDLED_CALIB, 'r', encoding='utf-8') as f:
                _cal_cache = yaml.safe_load(f) or {}
            if _cal_cache:
                return _cal_cache
        except Exception:
            pass

    _cal_cache = {}
    return _cal_cache


def _auto_set_tolerance(resolution):
    """根据分辨率自动设置像素匹配容差倍数"""
    try:
        from helper import image_helper as ih
        w, h = resolution
        dpi_ratio = max(w / 1920.0, h / 1080.0)
        if dpi_ratio > 1.8:
            ih.set_tolerance_scale(3.0)
        elif dpi_ratio > 1.2:
            ih.set_tolerance_scale(2.0)
    except Exception:
        pass


def get_ui(key: str, default: Any = None) -> Any:
    """获取 UI 元素的校准坐标"""
    cal = load_calibration()
    return cal.get('ui', {}).get(key, default)


def get_inventory_slot(col: int, row: int) -> tuple:
    """获取背包槽位坐标（自动校准）"""
    cal = load_calibration()
    inv = cal.get('ui', {}).get('inventory', {})
    first = inv.get('first_slot', {'x': 1420, 'y': 420})
    size = inv.get('slot_size', {'width': 55, 'height': 55})

    x = first['x'] + col * size['width']
    y = first['y'] + row * size['height']
    return x, y


def refresh_cache():
    """强制刷新缓存（校准后调用）"""
    global _cal_cache
    _cal_cache = None

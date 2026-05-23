"""
校准数据加载器 — 所有模块通过此接口获取坐标
优先级：calibration.yaml > 硬编码默认值
"""
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from typing import Dict, Any, Optional
import yaml

# Priorität: writable (neben EXE) > bundled (MEIPASS) > empty
if getattr(sys, "frozen", False):
    _WRITABLE_CALIB = Path(sys.executable).parent / "config" / "calibration.yaml"
else:
    _WRITABLE_CALIB = _ROOT / "config" / "calibration.yaml"
_BUNDLED_CALIB = _ROOT / "config" / "calibration.yaml"

_cal_cache = None  # 单例缓存


def load_calibration() -> Dict:
    """加载校准数据（带缓存）— 先 writable 后 bundled"""
    global _cal_cache
    if _cal_cache is not None:
        return _cal_cache

    # Check writable first (user recalibrated)
    if _WRITABLE_CALIB.exists():
        try:
            with open(_WRITABLE_CALIB, 'r', encoding='utf-8') as f:
                _cal_cache = yaml.safe_load(f) or {}
            return _cal_cache
        except Exception:
            pass

    # Fallback to bundled
    if _BUNDLED_CALIB.exists():
        try:
            with open(_BUNDLED_CALIB, 'r', encoding='utf-8') as f:
                _cal_cache = yaml.safe_load(f) or {}
            return _cal_cache
        except Exception:
            pass

    _cal_cache = {}
    return _cal_cache


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

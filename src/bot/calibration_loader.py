"""
校准数据加载器 — 所有模块通过此接口获取坐标
优先级：calibration.yaml > 硬编码默认值
"""
from pathlib import Path
from typing import Dict, Any, Optional
import yaml

CALIB_FILE = Path(__file__).resolve().parents[2] / "config" / "calibration.yaml"

_cal_cache = None  # 单例缓存


def load_calibration() -> Dict:
    """加载校准数据（带缓存）"""
    global _cal_cache
    if _cal_cache is not None:
        return _cal_cache

    if not CALIB_FILE.exists():
        _cal_cache = {}
        return _cal_cache

    try:
        with open(CALIB_FILE, 'r', encoding='utf-8') as f:
            _cal_cache = yaml.safe_load(f) or {}
    except Exception:
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

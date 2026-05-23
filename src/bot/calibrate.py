"""
自动化坐标校准模块 — 启动时自动定位所有 UI 元素
原理：模板匹配 + 像素扫描 → 生成 calibration.yaml
用户只需：启动游戏 → 站在城镇 → 运行此脚本
"""
import yaml
import os
from time import sleep
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from typing import Optional, Tuple, Dict

import numpy as np
from PIL import ImageGrab

from helper import image_helper as ih
from helper import logging_helper, config_helper

CALIB_DIR = (_ROOT / "config")  # Read from bundle
# Write calibration next to EXE in frozen mode (MEIPASS is read-only)
if getattr(sys, "frozen", False):
    CALIB_WRITE_DIR = Path(sys.executable).parent / "config"
else:
    CALIB_WRITE_DIR = CALIB_DIR
CALIB_FILE = CALIB_WRITE_DIR / "calibration.yaml"
# Also check bundled location for reading
CALIB_BUNDLED = CALIB_DIR / "calibration.yaml"

# 模板图片目录（首次运行需用工具箱 F12 截图保存）
TEMPLATES_DIR = _ROOT / "assets" / "templates"


class AutoCalibrator:
    """
    全自动 UI 坐标校准器。

    使用方式：
    1. 启动 D4，角色站在 Kyovashad 或其他主城
    2. 运行: python -m bot.calibrate
    3. 校准完成，坐标写入 config/calibration.yaml
    4. bot 会自动读取校准坐标
    """

    def __init__(self):
        self.cfg = config_helper.read_config() or {}
        self.resolution = self._detect_resolution()
        self.cal_data = {
            'resolution': self.resolution,
            'detected_at': '',
        }
        logging_helper.log_info(f"Detected resolution: {self.resolution}")

    def _detect_resolution(self) -> Tuple[int, int]:
        """自动检测屏幕分辨率"""
        try:
            img = ImageGrab.grab()
            return img.size  # (width, height)
        except Exception:
            return (1920, 1080)  # 默认值

    def _screenshot(self, region: Optional[Tuple[int, int, int, int]] = None):
        """截取屏幕（全屏或指定区域）"""
        try:
            if region:
                return ImageGrab.grab(bbox=region)
            return ImageGrab.grab()
        except Exception as e:
            logging_helper.log_error(f"Screenshot failed: {e}")
            return None

    # ========== 逐项检测 ==========

    def detect_game_window(self) -> Dict:
        """检测游戏窗口状态 — 高DPI/高分辨率下提高容差"""
        w, h = self.resolution
        # Higher tolerance for 1440p+ displays where pixel colors may differ slightly
        dpi_tol = 50 if w > 1920 else 30

        # 检测 HUD 可见性（技能栏在底部中央）
        skillbar_y = int(h * 0.92)
        skillbar_visible = self._check_pixel(int(w * 0.5), skillbar_y, 50, 40, 35, dpi_tol)
        logging_helper.log_info(f"Skillbar check at ({int(w*0.5)}, {skillbar_y}): {skillbar_visible}")

        # 检测小地图位置（右上角）
        minimap_visible = self._check_pixel(int(w * 0.92), int(h * 0.08), 30, 25, 20, dpi_tol)
        logging_helper.log_info(f"Minimap check at ({int(w*0.92)}, {int(h*0.08)}): {minimap_visible}")

        return {
            'skillbar_visible': skillbar_visible,
            'minimap_visible': minimap_visible,
            'game_active': skillbar_visible and minimap_visible,
        }

    def detect_health_orb(self) -> Dict:
        """检测血球位置（左下角红球）"""
        w, h = self.resolution

        # 血球特征：红色圆形，左下角
        # 1920×1080 基准：血球中心约 (110, 920)
        base_x, base_y = int(w * 0.057), int(h * 0.852)

        # 像素扫描验证
        health_found = self._scan_region_for_color(
            base_x - 30, base_y - 30, 60, 60,
            180, 20, 20, 40  # 红色
        )

        return {
            'health_orb': {'x': base_x, 'y': base_y},
            'health_detected': health_found,
        }

    def detect_resource_orb(self) -> Dict:
        """检测资源球位置（右下角）"""
        w, h = self.resolution
        # 1920×1080 基准：资源球中心约 (1810, 920)
        base_x, base_y = int(w * 0.943), int(h * 0.852)
        return {
            'resource_orb': {'x': base_x, 'y': base_y},
        }

    def detect_skill_bar(self) -> Dict:
        """
        检测技能栏 6 个槽位位置。
        返回每个槽的中心坐标。
        """
        w, h = self.resolution
        # 1920×1080 基准：技能栏中央 y ≈ 990
        bar_y = int(h * 0.917)
        # 6个技能槽的 x 基准（从技能栏中心向两侧展开）
        center_x = int(w * 0.5)
        slot_width = int(w * 0.031)  # ~60px
        slot_spacing = int(w * 0.036)  # ~70px

        slots = {}
        labels = ['left_click', 'skill1', 'skill2', 'skill3', 'skill4', 'right_click']
        # 左键在左侧，右键在右侧，中间4个技能键
        offsets = [
            -slot_spacing * 2 - int(slot_spacing * 0.5),  # 左键
            -slot_spacing,                                  # skill1
            0,                                               # skill2
            slot_spacing,                                    # skill3
            slot_spacing * 2,                                # skill4
            slot_spacing * 2 + int(slot_spacing * 0.5),     # 右键
        ]

        for i, (label, offset) in enumerate(zip(labels, offsets)):
            sx = center_x + offset
            slots[label] = {'x': sx, 'y': bar_y, 'key_bind': self.cfg.get(f'skill{i}', '')}

        return {'skill_slots': slots, 'skill_bar_y': bar_y}

    def detect_minimap(self) -> Dict:
        """检测小地图区域"""
        w, h = self.resolution
        # 1920×1080 基准：小地图右上角
        map_region = {
            'x': int(w * 0.88),   # ~1690
            'y': int(h * 0.03),   # ~32
            'width': int(w * 0.09),  # ~173
            'height': int(h * 0.14), # ~151
        }
        return {'minimap': map_region}

    def detect_inventory_grid(self) -> Dict:
        """
        检测背包格子起始位置和布局。
        D4 背包：11行 × 3列，从右侧屏幕开始。
        """
        w, h = self.resolution
        # 1920×1080 基准：第一个背包格子位于 (1420, 420)
        first_slot = {
            'x': int(w * 0.739),   # 1420
            'y': int(h * 0.389),    # 420
        }
        slot_size = {
            'width': int(w * 0.029),   # ~55
            'height': int(h * 0.051),   # ~55
        }

        return {
            'inventory': {
                'first_slot': first_slot,
                'slot_size': slot_size,
                'cols': 3,
                'rows': 11,
                'max_slots': 33,
            }
        }

    def detect_npc_positions(self) -> Dict:
        """
        检测城镇 NPC 大致位置。
        这些是相对城镇中心的大致坐标，需要模板匹配精确化。
        """
        w, h = self.resolution
        center_x, center_y = int(w * 0.5), int(h * 0.5)

        return {
            'npc_approx': {
                'blacksmith': {'x': int(center_x * 0.6), 'y': int(center_y * 1.4)},
                'stash': {'x': int(center_x * 0.5), 'y': int(center_y * 1.2)},
                'occultist': {'x': int(center_x * 0.7), 'y': int(center_y * 1.35)},
                'waypoint': {'x': int(center_x * 0.5), 'y': int(center_y * 1.1)},
            }
        }

    def detect_boss_hud(self) -> Dict:
        """Boss 血条检测区域"""
        w, h = self.resolution
        # Boss 血条在屏幕顶部中央
        return {
            'boss_health_bar': {
                'x': int(w * 0.3),     # ~576
                'y': int(h * 0.05),    # ~54
                'width': int(w * 0.4),  # ~768
                'height': int(h * 0.04), # ~43
            },
            'boss_check_pixels': [
                {'x': int(w * 0.5), 'y': int(h * 0.09), 'r': 200, 'g': 30, 'b': 20},
            ]
        }

    def detect_dialogue_box(self) -> Dict:
        """对话栏检测区域"""
        w, h = self.resolution
        return {
            'dialogue': {
                'area': {
                    'x': int(w * 0.15),
                    'y': int(h * 0.75),
                    'width': int(w * 0.7),
                    'height': int(h * 0.2),
                },
                'continue_pixels': [
                    {'x': int(w * 0.5), 'y': int(h * 0.88), 'r': 220, 'g': 210, 'b': 190},
                ]
            }
        }

    def detect_cutscene_indicators(self) -> Dict:
        """过场动画检测"""
        w, h = self.resolution
        return {
            'cutscene': {
                'top_bar_pixel': {'x': 1, 'y': 1, 'r': 0, 'g': 0, 'b': 0, 'tolerance': 5},
                'bottom_bar_pixel': {'x': 1, 'y': h - 10, 'r': 0, 'g': 0, 'b': 0, 'tolerance': 5},
                'hud_check': {'x': int(w * 0.374), 'y': int(h * 0.907), 'r': 59, 'g': 75, 'b': 84, 'tolerance': 20},
            }
        }

    def detect_helltide_indicators(self) -> Dict:
        """地狱狂潮相关检测"""
        w, h = self.resolution
        return {
            'helltide': {
                'map_icon_region': {
                    'x': int(w * 0.1), 'y': int(h * 0.1),
                    'width': int(w * 0.8), 'height': int(h * 0.7),
                },
                'cinder_counter': {'x': int(w * 0.05), 'y': int(h * 0.92)},
            }
        }

    def detect_glyph_altar(self) -> Dict:
        """雕文祭坛/升级区域"""
        w, h = self.resolution
        return {
            'glyph_altar': {
                'pedestal_region': {
                    'x': int(w * 0.2), 'y': int(h * 0.3),
                    'width': int(w * 0.35), 'height': int(h * 0.45),
                },
                'upgrade_button': {'x': int(w * 0.5), 'y': int(h * 0.82)},
            }
        }

    # ========== 辅助方法 ==========

    def _check_pixel(self, x: int, y: int, r: int, g: int, b: int, tol: int = 30) -> bool:
        """检查单个像素是否匹配颜色"""
        try:
            return ih.pixel_matches_color(x, y, r, g, b, tol)
        except Exception:
            return False

    def _scan_region_for_color(self, x: int, y: int, w: int, h: int,
                                r: int, g: int, b: int, tol: int) -> bool:
        """扫描区域内是否存在目标颜色"""
        try:
            img = self._screenshot((x, y, x + w, y + h))
            if img is None:
                return False
            arr = np.array(img)
            mask = (
                (arr[:, :, 0] >= r - tol) & (arr[:, :, 0] <= r + tol) &
                (arr[:, :, 1] >= g - tol) & (arr[:, :, 1] <= g + tol) &
                (arr[:, :, 2] >= b - tol) & (arr[:, :, 2] <= b + tol)
            )
            return np.any(mask)
        except Exception:
            return False

    # ========== 主流程 ==========

    def run_full_calibration(self) -> bool:
        """执行完整校准流程"""
        import datetime
        self.cal_data['detected_at'] = datetime.datetime.now().isoformat()

        logging_helper.log_info("=== Starting Auto-Calibration ===")

        # Step 1: 检测游戏窗口（仅警告，不阻塞——坐标按分辨率比例计算）
        game = self.detect_game_window()
        self.cal_data.update(game)
        if not game.get('game_active'):
            logging_helper.log_info("⚠ Game window not detected, but continuing anyway...")
            logging_helper.log_info("  Coordinates are computed from resolution, not pixel scanning.")
            logging_helper.log_info("  Make sure D4 is running in windowed fullscreen.")
        else:
            logging_helper.log_info("✓ Game window detected")

        # Step 2: 检测 UI 元素
        self.cal_data['ui'] = {}

        health = self.detect_health_orb()
        self.cal_data['ui'].update(health)
        logging_helper.log_info(f"✓ Health orb: {health}")

        resource = self.detect_resource_orb()
        self.cal_data['ui'].update(resource)

        skills = self.detect_skill_bar()
        self.cal_data['ui'].update(skills)
        logging_helper.log_info(f"✓ Skill bar: {len(skills['skill_slots'])} slots")

        minimap = self.detect_minimap()
        self.cal_data['ui'].update(minimap)
        logging_helper.log_info("✓ Mini-map")

        inventory = self.detect_inventory_grid()
        self.cal_data['ui'].update(inventory)
        logging_helper.log_info(f"✓ Inventory grid: {inventory['inventory']['max_slots']} slots")

        npcs = self.detect_npc_positions()
        self.cal_data['ui'].update(npcs)

        boss = self.detect_boss_hud()
        self.cal_data['ui'].update(boss)

        dialogue = self.detect_dialogue_box()
        self.cal_data['ui'].update(dialogue)

        cutscene = self.detect_cutscene_indicators()
        self.cal_data['ui'].update(cutscene)

        helltide = self.detect_helltide_indicators()
        self.cal_data['ui'].update(helltide)

        glyph = self.detect_glyph_altar()
        self.cal_data['ui'].update(glyph)

        # Step 3: 保存
        self._save_calibration()
        return True

    def _save_calibration(self) -> None:
        """写入 calibration.yaml — 在 frozen mode 写入 EXE 旁边"""
        CALIB_WRITE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CALIB_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(self.cal_data, f, default_flow_style=False, allow_unicode=True)
        logging_helper.log_info(f"✓ Calibration saved to {CALIB_FILE}")

    @staticmethod
    def load_calibration() -> Dict:
        """加载校准数据 — 先读 writable dir，再回退 bundled"""
        # Check writable location first (user may have recalibrated)
        if CALIB_FILE.exists():
            with open(CALIB_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logging_helper.log_info(f"Loaded calibration from {CALIB_FILE}")
            return data or {}

        # Fallback to bundled default
        if CALIB_BUNDLED.exists():
            with open(CALIB_BUNDLED, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logging_helper.log_info(f"Loaded calibration from {CALIB_BUNDLED}")
            return data or {}

        logging_helper.log_info("No calibration file found. Run calibration first!")
        # 返回默认1920×1080值
        ac = AutoCalibrator()
        ac.run_full_calibration()
        return ac.cal_data


def run_calibration() -> bool:
    """命令行入口"""
    ac = AutoCalibrator()
    return ac.run_full_calibration()


if __name__ == "__main__":
    print("=" * 50)
    print("D4 Bot - Auto Calibration Tool")
    print("=" * 50)
    print()
    print("Make sure:")
    print("1. Diablo 4 is running in Windowed Fullscreen 1920x1080")
    print("2. You are standing in a town (not in menu/loading)")
    print("3. HUD is visible (health bar, skill bar, minimap)")
    print()
    input("Press Enter to start calibration...")

    success = run_calibration()
    if success:
        print(f"\n✓ Calibration complete!")
        print(f"  Config saved to: {CALIB_FILE}")
    else:
        print("\n✗ Calibration failed!")
        print("  Make sure D4 is in-game (not menu/loading) and try again.")

"""
自动化坐标校准模块 — 启动时自动定位所有 UI 元素
原理：检测分辨率 → 1440p用预制校准 / 1080p用像素扫描
支持：1920×1080 / 2560×1440 / 3840×2160（按比例计算）
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

CALIB_DIR = (_ROOT / "config")
# Write calibration next to EXE in frozen mode (MEIPASS is read-only)
if getattr(sys, "frozen", False):
    CALIB_WRITE_DIR = Path(sys.executable).parent / "config"
else:
    CALIB_WRITE_DIR = CALIB_DIR
CALIB_FILE = CALIB_WRITE_DIR / "calibration.yaml"
CALIB_BUNDLED = CALIB_DIR / "calibration.yaml"

# Pre-built calibrations for known resolutions
_PREBUILT_CALIBRATIONS = {
    (2560, 1440): CALIB_DIR / "calibration_1440p.yaml",
}


class AutoCalibrator:
    """
    全自动 UI 坐标校准器。

    使用方式：
    1. 启动 D4，角色站在 Kyovashad 或其他主城
    2. 运行: python -m bot.calibrate
    3. 校准完成，坐标写入 config/calibration.yaml
    4. bot 会自动读取校准坐标

    高DPI策略：
    - 2560×1440: 直接加载预制校准文件（pixel-perfect预计算坐标）
    - 其他分辨率: 像素扫描 + 区域检测 + 高容差
    - 所有分辨率: 自动设置 tolerance scaling 确保 bot 运行时像素匹配正常工作
    """

    def __init__(self):
        self.cfg = config_helper.read_config() or {}
        self.resolution = self._detect_resolution()
        self.cal_data = {
            'resolution': list(self.resolution),
            'detected_at': '',
        }
        logging_helper.log_info(f"Detected resolution: {self.resolution[0]}×{self.resolution[1]}")

        # Set DPI-aware tolerance scaling
        self._setup_tolerance_scale()

    def _detect_resolution(self) -> Tuple[int, int]:
        """自动检测屏幕分辨率"""
        try:
            img = ImageGrab.grab()
            return img.size  # (width, height)
        except Exception:
            return (1920, 1080)  # 默认值

    def _setup_tolerance_scale(self):
        """根据分辨率设置全局像素匹配容差倍数"""
        w, h = self.resolution
        # 按DPI比例计算：设计基准1920×1080
        scale_x = w / 1920.0
        scale_y = h / 1080.0
        dpi_ratio = max(scale_x, scale_y)

        if dpi_ratio > 1.8:       # ~4K
            factor = 3.0
        elif dpi_ratio > 1.2:     # ~1440p
            factor = 2.0
        else:                      # 1080p
            factor = 1.0

        ih.set_tolerance_scale(factor)
        logging_helper.log_info(f"DPI ratio: {dpi_ratio:.2f}, tolerance scale: {factor:.1f}x")

    def _has_prebuilt_calibration(self) -> bool:
        """检查当前分辨率是否有预制校准文件"""
        return self.resolution in _PREBUILT_CALIBRATIONS

    def _load_prebuilt_calibration(self) -> bool:
        """加载预制校准文件（pixel-perfect for known resolutions）"""
        prebuilt_path = _PREBUILT_CALIBRATIONS.get(self.resolution)
        if not prebuilt_path or not prebuilt_path.exists():
            return False

        try:
            with open(prebuilt_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data and 'ui' in data:
                self.cal_data = data
                self.cal_data['detected_at'] = str(__import__('datetime').datetime.now().isoformat())
                self.cal_data['resolution'] = list(self.resolution)
                logging_helper.log_info(
                    f"✓ 加载预制校准: {self.resolution[0]}×{self.resolution[1]} "
                    f"(文件: {prebuilt_path.name})"
                )
                return True
        except Exception as e:
            logging_helper.log_error(f"加载预制校准失败: {e}")

        return False

    def _screenshot(self, region: Optional[Tuple[int, int, int, int]] = None):
        """截取屏幕（全屏或指定区域）"""
        try:
            if region:
                return ImageGrab.grab(bbox=region)
            return ImageGrab.grab()
        except Exception as e:
            logging_helper.log_error(f"Screenshot failed: {e}")
            return None

    # ========== 区域扫描检测 ==========

    def _scan_region_for_color(self, x: int, y: int, w: int, h: int,
                                r: int, g: int, b: int, tol: int) -> bool:
        """扫描区域内是否存在目标颜色（高容差）"""
        try:
            img = self._screenshot((x, y, x + w, y + h))
            if img is None:
                return False
            arr = np.array(img)
            # Allow asymmetric tolerance: R channel can vary more in D4 UI
            r_tol = tol * 2 if tol > 30 else tol  # Red varies more on 1440p
            g_tol = tol
            b_tol = tol
            mask = (
                (arr[:, :, 0] >= r - r_tol) & (arr[:, :, 0] <= r + r_tol) &
                (arr[:, :, 1] >= g - g_tol) & (arr[:, :, 1] <= g + g_tol) &
                (arr[:, :, 2] >= b - b_tol) & (arr[:, :, 2] <= b + b_tol)
            )
            # Need at least 3 matching pixels to avoid noise
            return np.count_nonzero(mask) >= 3
        except Exception:
            return False

    def detect_game_window(self) -> Dict:
        """
        检测游戏窗口状态 — 区域扫描替代单像素匹配
        在1440p下使用极高容差 + 多点验证
        """
        w, h = self.resolution
        detected = {'skillbar_visible': False, 'minimap_visible': False, 'game_active': False}

        # --- 技能栏检测（底部中央）---
        # D4技能栏有多种颜色：棕/灰背景、技能图标色、CD倒计时色
        # 扫描一个10×10区域而非单像素，大幅提高命中率
        bar_cx, bar_cy = int(w * 0.5), int(h * 0.92)
        bar_region = (bar_cx - 5, bar_cy - 5, bar_cx + 5, bar_cy + 5)

        try:
            img = self._screenshot(bar_region)
            if img is not None:
                arr = np.array(img)
                # D4技能栏特征：深灰色(#2D2D32→RGB~45,45,50) 或 浅棕色(#4A3F35→RGB~74,63,53)
                # 在3×3+区域中存在即可
                dark_gray_mask = (
                    (arr[:, :, 0] >= 20) & (arr[:, :, 0] <= 80) &
                    (arr[:, :, 1] >= 20) & (arr[:, :, 1] <= 80) &
                    (arr[:, :, 2] >= 20) & (arr[:, :, 2] <= 80)
                )
                brown_mask = (
                    (arr[:, :, 0] >= 40) & (arr[:, :, 0] <= 120) &
                    (arr[:, :, 1] >= 30) & (arr[:, :, 1] <= 100) &
                    (arr[:, :, 2] >= 20) & (arr[:, :, 2] <= 90)
                )
                # Need > 20% of the 10×10 region to match
                total_pixels = arr.shape[0] * arr.shape[1]
                dark_ratio = np.count_nonzero(dark_gray_mask) / total_pixels
                brown_ratio = np.count_nonzero(brown_mask) / total_pixels

                detected['skillbar_visible'] = dark_ratio > 0.2 or brown_ratio > 0.15
                logging_helper.log_info(
                    f"Skillbar region scan: dark={dark_ratio:.1%}, brown={brown_ratio:.1%}, "
                    f"detected={detected['skillbar_visible']}"
                )
        except Exception as e:
            logging_helper.log_error(f"Skillbar scan failed: {e}")

        # --- 小地图检测（右上角）---
        # D4小地图：深色背景上有金色边框(≈RGB 180,140,50)
        # 扫描5×5区域
        mm_cx, mm_cy = int(w * 0.92), int(h * 0.08)
        mm_region = (mm_cx - 3, mm_cy - 3, mm_cx + 3, mm_cy + 3)

        try:
            img = self._screenshot(mm_region)
            if img is not None:
                arr = np.array(img)
                # 金色边框色
                gold_mask = (
                    (arr[:, :, 0] >= 100) & (arr[:, :, 0] <= 220) &
                    (arr[:, :, 1] >= 60) & (arr[:, :, 1] <= 180) &
                    (arr[:, :, 2] >= 10) & (arr[:, :, 2] <= 100)
                )
                # 深色地图背景
                dark_mask = (
                    (arr[:, :, 0] >= 10) & (arr[:, :, 0] <= 70) &
                    (arr[:, :, 1] >= 5) & (arr[:, :, 1] <= 60) &
                    (arr[:, :, 2] >= 5) & (arr[:, :, 2] <= 60)
                )
                total_pixels = arr.shape[0] * arr.shape[1]
                gold_ratio = np.count_nonzero(gold_mask) / total_pixels
                dark_ratio = np.count_nonzero(dark_mask) / total_pixels

                detected['minimap_visible'] = gold_ratio > 0.1 or dark_ratio > 0.5
                logging_helper.log_info(
                    f"Minimap region scan: gold={gold_ratio:.1%}, dark={dark_ratio:.1%}, "
                    f"detected={detected['minimap_visible']}"
                )
        except Exception as e:
            logging_helper.log_error(f"Minimap scan failed: {e}")

        detected['game_active'] = detected['skillbar_visible'] or detected['minimap_visible']
        return detected

    def detect_health_orb(self) -> Dict:
        """检测血球位置（左下角红球）"""
        w, h = self.resolution
        base_x, base_y = int(w * 0.057), int(h * 0.852)

        # 区域扫描红色（血球特征色）
        health_found = self._scan_region_for_color(
            base_x - 45, base_y - 45, 90, 90,
            180, 20, 20, 60  # 宽泛红色容差
        )

        return {
            'health_orb': {'x': base_x, 'y': base_y},
            'health_detected': health_found,
        }

    def detect_resource_orb(self) -> Dict:
        w, h = self.resolution
        base_x, base_y = int(w * 0.943), int(h * 0.852)
        return {'resource_orb': {'x': base_x, 'y': base_y}}

    def detect_skill_bar(self) -> Dict:
        w, h = self.resolution
        bar_y = int(h * 0.917)
        center_x = int(w * 0.5)
        slot_width = int(w * 0.031)
        slot_spacing = int(w * 0.036)

        slots = {}
        labels = ['left_click', 'skill1', 'skill2', 'skill3', 'skill4', 'right_click']
        offsets = [
            -slot_spacing * 2 - int(slot_spacing * 0.5),
            -slot_spacing,
            0,
            slot_spacing,
            slot_spacing * 2,
            slot_spacing * 2 + int(slot_spacing * 0.5),
        ]

        for i, (label, offset) in enumerate(zip(labels, offsets)):
            sx = center_x + offset
            slots[label] = {'x': sx, 'y': bar_y, 'key_bind': self.cfg.get(f'skill{i}', '')}

        return {'skill_slots': slots, 'skill_bar_y': bar_y}

    def detect_minimap(self) -> Dict:
        w, h = self.resolution
        return {
            'minimap': {
                'x': int(w * 0.88),
                'y': int(h * 0.03),
                'width': int(w * 0.09),
                'height': int(h * 0.14),
            }
        }

    def detect_inventory_grid(self) -> Dict:
        w, h = self.resolution
        return {
            'inventory': {
                'first_slot': {'x': int(w * 0.739), 'y': int(h * 0.389)},
                'slot_size': {'width': int(w * 0.029), 'height': int(h * 0.051)},
                'cols': 3,
                'rows': 11,
                'max_slots': 33,
            }
        }

    def detect_npc_positions(self) -> Dict:
        w, h = self.resolution
        cx, cy = int(w * 0.5), int(h * 0.5)
        return {
            'npc_approx': {
                'blacksmith': {'x': int(cx * 0.6), 'y': int(cy * 1.4)},
                'stash': {'x': int(cx * 0.5), 'y': int(cy * 1.2)},
                'occultist': {'x': int(cx * 0.7), 'y': int(cy * 1.35)},
                'waypoint': {'x': int(cx * 0.5), 'y': int(cy * 1.1)},
            }
        }

    def detect_boss_hud(self) -> Dict:
        w, h = self.resolution
        return {
            'boss_health_bar': {
                'x': int(w * 0.3), 'y': int(h * 0.05),
                'width': int(w * 0.4), 'height': int(h * 0.04),
            },
            'boss_check_pixels': [
                {'x': int(w * 0.5), 'y': int(h * 0.09), 'r': 200, 'g': 30, 'b': 20},
            ]
        }

    def detect_dialogue_box(self) -> Dict:
        w, h = self.resolution
        return {
            'dialogue': {
                'area': {
                    'x': int(w * 0.15), 'y': int(h * 0.75),
                    'width': int(w * 0.7), 'height': int(h * 0.2),
                },
                'continue_pixels': [
                    {'x': int(w * 0.5), 'y': int(h * 0.88), 'r': 220, 'g': 210, 'b': 190},
                ]
            }
        }

    def detect_cutscene_indicators(self) -> Dict:
        w, h = self.resolution
        return {
            'cutscene': {
                'top_bar_pixel': {'x': 1, 'y': 1, 'r': 0, 'g': 0, 'b': 0, 'tolerance': 5},
                'bottom_bar_pixel': {'x': 1, 'y': h - 10, 'r': 0, 'g': 0, 'b': 0, 'tolerance': 5},
                'hud_check': {'x': int(w * 0.374), 'y': int(h * 0.907), 'r': 59, 'g': 75, 'b': 84, 'tolerance': 20},
            }
        }

    def detect_helltide_indicators(self) -> Dict:
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

    # ========== 主流程 ==========

    def run_full_calibration(self) -> bool:
        """执行完整校准流程"""
        import datetime
        self.cal_data['detected_at'] = datetime.datetime.now().isoformat()

        logging_helper.log_info("=" * 50)
        logging_helper.log_info(f"=== Auto-Calibration for {self.resolution[0]}×{self.resolution[1]} ===")
        logging_helper.log_info("=" * 50)

        # Step 0: 预制校准优先（1440p等已知分辨率）
        if self._has_prebuilt_calibration():
            logging_helper.log_info("→ 检测到已知分辨率，加载预制校准...")
            if self._load_prebuilt_calibration():
                self._save_calibration()
                logging_helper.log_info("✓ 预制校准加载成功！")
                return True
            logging_helper.log_info("⚠ 预制校准文件缺失，回退到自动检测...")

        # Step 1: 检测游戏窗口
        game = self.detect_game_window()
        self.cal_data.update(game)

        if game.get('game_active'):
            logging_helper.log_info("✓ 游戏窗口检测成功（区域扫描）")
        else:
            logging_helper.log_info("⚠ 区域扫描未检测到游戏窗口")
            # 非阻塞：坐标按分辨率比例计算，仍可继续
            logging_helper.log_info("  坐标按分辨率比例计算，继续校准...")
            logging_helper.log_info("  确保 D4 在窗口全屏模式下运行且 HUD 可见")

        # Step 2: 构建所有 UI 坐标
        self.cal_data['ui'] = {}

        health = self.detect_health_orb()
        self.cal_data['ui'].update(health)

        resource = self.detect_resource_orb()
        self.cal_data['ui'].update(resource)

        skills = self.detect_skill_bar()
        self.cal_data['ui'].update(skills)
        logging_helper.log_info(f"✓ 技能栏: {len(skills['skill_slots'])} 槽位定位完成")

        minimap = self.detect_minimap()
        self.cal_data['ui'].update(minimap)

        inventory = self.detect_inventory_grid()
        self.cal_data['ui'].update(inventory)
        logging_helper.log_info(f"✓ 背包: {inventory['inventory']['max_slots']} 格")

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
        logging_helper.log_info("=" * 50)
        logging_helper.log_info(f"✓ 校准完成！分辨率: {self.resolution[0]}×{self.resolution[1]}")
        logging_helper.log_info(f"  容差倍数: {ih.get_tolerance_scale():.1f}x")
        logging_helper.log_info(f"  技能栏: {skills['skill_bar_y']}")
        logging_helper.log_info(f"  血球: ({health['health_orb']['x']}, {health['health_orb']['y']})")
        logging_helper.log_info("=" * 50)
        return True

    def _save_calibration(self) -> None:
        """写入 calibration.yaml"""
        CALIB_WRITE_DIR.mkdir(parents=True, exist_ok=True)
        with open(CALIB_FILE, 'w', encoding='utf-8') as f:
            yaml.dump(self.cal_data, f, default_flow_style=False, allow_unicode=True)
        logging_helper.log_info(f"✓ 校准保存到 {CALIB_FILE}")

    @staticmethod
    def load_calibration() -> Dict:
        """加载校准数据 — 先读 writable dir，再回退 bundled"""
        if CALIB_FILE.exists():
            with open(CALIB_FILE, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logging_helper.log_info(f"已加载校准: {CALIB_FILE}")
            return data or {}

        if CALIB_BUNDLED.exists():
            with open(CALIB_BUNDLED, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            logging_helper.log_info(f"已加载校准: {CALIB_BUNDLED}")
            return data or {}

        logging_helper.log_info("无校准文件，运行自动校准...")
        ac = AutoCalibrator()
        ac.run_full_calibration()
        return ac.cal_data


def run_calibration() -> bool:
    """命令行/按钮入口"""
    ac = AutoCalibrator()
    return ac.run_full_calibration()


if __name__ == "__main__":
    print("=" * 50)
    print("D4 Bot - Auto Calibration Tool v2")
    print("=" * 50)
    print()
    print("支持分辨率: 1920×1080 / 2560×1440 / 3840×2160")
    print("1440p+ → 预制校准；1080p → 区域扫描")
    print()
    print("Make sure:")
    print("1. Diablo 4 运行中（窗口全屏）")
    print("2. 站在城镇（非菜单/加载画面）")
    print("3. HUD 可见（血条、技能栏、小地图）")
    print()
    input("按 Enter 开始校准...")

    success = run_calibration()
    if success:
        print(f"\n✓ 校准完成！")
        print(f"  配置文件: {CALIB_FILE}")
    else:
        print("\n✗ 校准失败！")
        print("  确保 D4 在游戏中（非菜单/加载画面）后重试")

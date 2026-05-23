"""
梦魇地城模块 — 钥石消耗→进入→清图→Boss→雕文升级
复用现有战斗轮转和寻路模块
"""
from time import sleep
from random import uniform
from typing import Optional, Tuple
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
import yaml

from pydirectinput import leftClick, rightClick, press
from helper import mouse_helper, image_helper, config_helper, logging_helper
from bot import rotation, pather, pickit

CONFIG_DIR = _ROOT / "config"
ASSETS_DIR = _ROOT / "assets"

# === 地城常量 ===
GLYPH_ALTAR_REGION = (400, 300, 700, 500)   # 雕文祭坛屏幕区域
BOSS_HUD_PIXELS = [(960, 100, 200, 30, 20, 30)]  # Boss 血条检测
DUNGEON_COMPLETE_PIXELS = [(960, 400, 200, 180, 80, 30)]  # 地城完成提示


class DungeonRunner:
    """梦魇地城自动运行器"""

    def __init__(self):
        self.cfg = config_helper.read_config() or {}
        self.class_name = self.cfg.get('class', 'barbarian').lower()
        self._glyphs_config = self._load_glyphs()
        self._dungeon_attempts = 0
        self._boss_killed = False

    def _load_glyphs(self) -> dict:
        path = CONFIG_DIR / "glyphs.yaml"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    # === 状态检测 ===

    def is_in_dungeon(self) -> bool:
        """检测是否在地城内（小地图样式 + 任务指示器）"""
        # 地城内小地图有特殊边框和楼层显示
        checks = [
            (1750, 50, 40, 40, 40, 20),   # 小地图边框
        ]
        for x, y, r, g, b, tol in checks:
            if image_helper.pixel_matches_color(x, y, r, g, b, tol):
                return True
        return False

    def is_boss_room(self) -> bool:
        """检测是否进入 Boss 房间（大门/封闭区域）"""
        # Boss 血条出现在屏幕顶部
        return any(
            image_helper.pixel_matches_color(x, y, r, g, b, tol)
            for x, y, r, g, b, tol in BOSS_HUD_PIXELS
        )

    def is_dungeon_complete(self) -> bool:
        """检测地城是否完成（完成提示/升级柱出现）"""
        return any(
            image_helper.pixel_matches_color(x, y, r, g, b, tol)
            for x, y, r, g, b, tol in DUNGEON_COMPLETE_PIXELS
        )

    def is_glyph_on_ground(self) -> bool:
        """检测地上是否有雕文掉落"""
        # 雕文掉落光柱（紫色）
        # 检测地面区域是否有紫色光柱
        ground_region = (300, 500, 1300, 400)
        try:
            # 简单颜色检测 — 紫色像素簇
            checks = [
                (500, 600, 180, 50, 200, 30),
                (700, 600, 180, 50, 200, 30),
                (900, 600, 180, 50, 200, 30),
            ]
            for x, y, r, g, b, tol in checks:
                if image_helper.pixel_matches_color(x, y, r, g, b, tol):
                    return True
        except Exception:
            pass
        return False

    # === 自动化操作 ===

    def consume_sigil(self) -> bool:
        """
        打开背包，右键钥石消耗。
        返回 True 表示成功消耗。
        """
        press('i')
        sleep(uniform(0.3, 0.5))

        # 切换到钥石标签（消耗品页）
        # 钥石通常在消耗品页的第一个位置
        # 简化版：点击假定位置
        leftClick(1620, 300)  # 右侧钥石标签
        sleep(uniform(0.2, 0.3))

        # 右键钥石（第一个格子）
        rightClick(1450, 450)
        sleep(uniform(0.2, 0.3))

        press('esc')  # 关闭背包
        sleep(uniform(0.3, 0.5))
        return True

    def enter_dungeon(self) -> bool:
        """
        点击地城入口。
        钥石消耗后地图上会出现入口标记。
        """
        # 打开地图找入口（红色地城图标）
        press('tab')
        sleep(uniform(0.3, 0.5))

        # 检测地城入口图标（红色菱形）
        dungeon_region = (200, 200, 1520, 680)
        try:
            x, y = image_helper.locate_needle(
                str(ASSETS_DIR / 'skills' / 'dungeon_entrance.png'),
                conf=0.7, region=dungeon_region
            )
            if x is not None and y is not None:
                rightClick(x, y)  # 右键传送/导航
                sleep(uniform(0.5, 0.8))
                press('tab')  # 关闭地图
                return True
        except Exception:
            pass

        press('tab')  # 关闭地图
        return False

    def navigate_to_objective(self) -> None:
        """在地城内导航到目标"""
        # 复用现有寻路 — 跟随小地图指示
        for _ in range(30):  # 最多尝试30次
            if self.is_boss_room():
                return

            # 检测敌人并战斗
            try:
                mob = image_helper.detect_lines('mob')
                if mob:
                    x, y, w, h = mob
                    rotation.rotation(x, y)
                    pickit.pick_it()  # 顺手捡
                    continue
            except Exception:
                pass

            # 移动（跟随小地图路径）
            pather.move_to_ref_location()
            sleep(uniform(0.1, 0.2))

    def hunt_boss(self) -> bool:
        """Boss 战 — 持续战斗直到 Boss 死亡"""
        logging_helper.log_info("=== BOSS FIGHT ===")
        fight_time = 0

        while fight_time < 120:  # 最多打2分钟
            if not self.is_boss_room() and self.is_dungeon_complete():
                logging_helper.log_info("Boss defeated!")
                self._boss_killed = True
                return True

            try:
                mob = image_helper.detect_lines('mob')
                if mob:
                    x, y, w, h = mob
                    rotation.rotation(x, y)  # 复用战斗轮转
            except Exception:
                pass

            # 喝药/闪避由 rotation 模块自动处理
            sleep(uniform(0.05, 0.1))
            fight_time += 0.1

        logging_helper.log_info("Boss fight timeout — continuing")
        return self._boss_killed

    def collect_glyph(self) -> bool:
        """拾取地上雕文"""
        if not self.is_glyph_on_ground():
            return False

        # 点击雕文光柱中心区域
        leftClick(960, 550)  # 中央区域
        sleep(uniform(0.3, 0.5))
        return True

    def upgrade_glyphs(self) -> None:
        """在雕文祭坛升级雕文"""
        # 检测升级柱
        try:
            pedestal_found = image_helper.locate_needle(
                str(ASSETS_DIR / 'skills' / 'upgrade_pedestal.png'),
                conf=0.7, region=GLYPH_ALTAR_REGION
            )
            if pedestal_found:
                x, y = pedestal_found
                if x is not None and y is not None:
                    leftClick(x, y)
                    sleep(uniform(1.0, 1.5))
        except Exception:
            # 祭坛图像未配置，使用默认位置
            leftClick(960, 540)
            sleep(uniform(1.0, 1.5))

        # 升级雕文（按优先级）
        glyphs = self._glyphs_config.get('glyphs', {}).get(self.class_name, [])

        for glyph in sorted(glyphs, key=lambda g: g.get('priority', 99)):
            # 选择雕文（点击雕文列表中的目标）
            # 简化：连续点击升级按钮
            # 完整版需要识别雕文名称然后选择
            name = glyph.get('name', '')
            logging_helper.log_info(f"Upgrading glyph: {name} (priority {glyph.get('priority')})")

            # 点击升级按钮（需要模板匹配或固定坐标）
            leftClick(960, 800)  # 升级按钮大致位置
            sleep(uniform(0.3, 0.5))

        # 退出祭坛
        press('esc')
        sleep(uniform(0.5, 0.8))

    def exit_dungeon(self) -> None:
        """离开地城 — 点击出口或使用升阶柱传送"""
        if self.is_dungeon_complete():
            # 地城完成 — 交互升阶柱
            press('f')  # 交互
            sleep(uniform(0.5, 1.0))
            # 通常升阶柱会提供一个"离开地城"选项
            leftClick(960, 600)
            sleep(uniform(3.0, 5.0))  # 加载

    # === 完整流程 ===

    def run_dungeon(self, max_dungeons: int = 1) -> None:
        """
        运行梦魇地城完整流程。
        """
        for i in range(max_dungeons):
            logging_helper.log_info(f"=== Nightmare Dungeon Run {i+1}/{max_dungeons} ===")
            self._dungeon_attempts += 1
            self._boss_killed = False

            # 1. 消耗钥石
            if not self.consume_sigil():
                logging_helper.log_error("Failed to consume sigil")
                break

            # 2. 进入地城
            if not self.enter_dungeon():
                logging_helper.log_error("Failed to enter dungeon")
                break

            sleep(uniform(2.0, 3.0))  # 等待加载

            # 3. 清图导航
            self.navigate_to_objective()

            # 4. Boss 战
            if self.is_boss_room() or self._boss_killed:
                self.hunt_boss()

            # 5. 拾取雕文
            self.collect_glyph()

            # 6. 升级雕文
            if self.is_dungeon_complete():
                self.upgrade_glyphs()

            # 7. 离开
            sleep(uniform(1.0, 2.0))
            self.exit_dungeon()

            logging_helper.log_info(f"=== Dungeon Run {i+1} complete ===")
            sleep(uniform(2.0, 3.0))


# 便捷函数 — 供 manager.py 调用

def run_nightmare_dungeon(max_runs: int = 1) -> None:
    """便捷入口"""
    runner = DungeonRunner()
    runner.run_dungeon(max_dungeons=max_runs)

"""
剧情模式模块 — 自动跟随任务推进主线
处理 NPC 对话、过场动画、任务目标导航
"""
from time import sleep
from random import uniform
from typing import Optional, Tuple
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]

from pydirectinput import leftClick, rightClick, press
from helper import image_helper, config_helper, logging_helper
from helper.image_helper import scale_x, scale_y, scale_region
from bot import rotation, pather, pickit

ASSETS_DIR = _ROOT / "assets"


class CampaignRunner:
    """剧情自动推图器"""

    def __init__(self):
        self.cfg = config_helper.read_config() or {}
        self._quest_name = ""
        self._cutscene_active = False
        self._dialogue_active = False

    # === 状态检测 ===

    def is_dialogue_active(self) -> bool:
        """检测是否在 NPC 对话中（对话框可见）"""
        # 对话栏在屏幕底部中央
        checks = [
            (scale_x(960), scale_y(850), 50, 45, 40, 20),   # 灰色对话背景
            (scale_x(960), scale_y(870), 220, 210, 190, 25), # 对话文字区域
        ]
        for x, y, r, g, b, tol in checks:
            if image_helper.pixel_matches_color(x, y, r, g, b, tol):
                return True
        return False

    def is_cutscene_active(self) -> bool:
        """检测是否在过场动画中"""
        # 过场：画面上下有黑边，无 HUD
        checks = [
            (scale_x(1), scale_y(1), 0, 0, 0, 5),       # 顶边黑色
            (scale_x(1), scale_y(1070), 0, 0, 0, 5),    # 底边黑色
            (scale_x(718), scale_y(980), 60, 75, 84, 30), # HUD 消失（无技能栏）
        ]
        hud_visible = image_helper.pixel_matches_color(scale_x(718), scale_y(980), 59, 75, 84, 20)
        if not hud_visible:
            return True
        return False

    def is_interaction_prompt(self) -> bool:
        """检测是否有交互提示（"按F交谈"等）"""
        # 屏幕中心偏下的交互提示
        checks = [
            (scale_x(960), scale_y(700), 220, 220, 200, 25),  # 白色交互文字
            (scale_x(960), scale_y(700), 240, 240, 220, 25),
        ]
        for x, y, r, g, b, tol in checks:
            if image_helper.pixel_matches_color(x, y, r, g, b, tol):
                return True
        return False

    def has_quest_marker(self) -> bool:
        """
        小地图上是否有任务标记。
        任务标记通常是黄色/金色箭头。
        """
        # 检查小地图区域的颜色点（简化为像素颜色检测）
        map_region = scale_region((1700, 80, 200, 180))  # 小地图区域
        # 黄色任务标记
        checks = [
            (scale_x(1750), scale_y(120), 255, 220, 50, 25),  # 黄色
            (scale_x(1780), scale_y(140), 255, 220, 50, 25),
            (scale_x(1730), scale_y(100), 255, 220, 50, 25),
        ]
        for x, y, r, g, b, tol in checks:
            if image_helper.pixel_matches_color(x, y, r, g, b, tol):
                return True

        # 备选：红色任务圈
        for x, y in [(scale_x(1750), scale_y(150)), (scale_x(1770), scale_y(130)), (scale_x(1730), scale_y(110))]:
            if image_helper.pixel_matches_color(x, y, 220, 40, 20, 25):
                return True

        return False

    # === 自动化操作 ===

    def handle_dialogue(self) -> None:
        """
        处理 NPC 对话。
        - 无选项 → 按 Space/Esc 继续
        - 有选项 → 选第一个（大多数剧情不需要特定选择）
        """
        if not self.is_dialogue_active():
            return

        logging_helper.log_info("Handling dialogue...")

        # 尝试检测是否有多个选项
        # 简化：直接按 Space 跳过
        for _ in range(10):
            if not self.is_dialogue_active():
                break
            press('space')  # D4 默认跳过/继续对话
            sleep(uniform(0.3, 0.5))

        self._dialogue_active = False
        logging_helper.log_info("Dialogue handled")

    def handle_cutscene(self) -> None:
        """等待过场动画结束"""
        if not self.is_cutscene_active():
            return

        logging_helper.log_info("Cutscene detected — waiting...")
        self._cutscene_active = True

        # 持续检测 HUD 恢复
        timeout = 0
        while timeout < 120:  # 最多等2分钟
            # 检测 HUD 是否恢复
            hud_visible = image_helper.pixel_matches_color(scale_x(718), scale_y(980), 59, 75, 84, 20)
            if hud_visible:
                logging_helper.log_info("Cutscene ended")
                self._cutscene_active = False
                return

            # 尝试按 Esc 跳过（部分过场可跳）
            if timeout > 3:
                press('esc')
                sleep(uniform(0.5, 1.0))
                # 检查是否弹出了跳过确认
                if image_helper.pixel_matches_color(scale_x(960), scale_y(600), 40, 40, 40, 20):
                    leftClick(scale_x(960), scale_y(600))  # 确认跳过
                    sleep(uniform(0.5, 1.0))

            sleep(uniform(0.5, 1.0))
            timeout += 1

    def handle_interaction(self) -> None:
        """处理交互提示（按F）"""
        if self.is_interaction_prompt():
            press('f')
            sleep(uniform(0.5, 0.8))
            logging_helper.log_info("Interaction performed")

    def follow_quest_marker(self) -> None:
        """跟随任务标记移动"""
        if not self.has_quest_marker():
            return

        logging_helper.log_info("Following quest marker")

        # 沿路移动 + 战斗 + 拾取
        for _ in range(40):
            # 检查是否到达（交互提示出现 = 到达目标）
            if self.is_interaction_prompt():
                return

            # 检查对话
            if self.is_dialogue_active():
                return

            # 检查过场
            if self.is_cutscene_active():
                return

            # 战斗
            try:
                mob = image_helper.detect_lines('mob')
                if mob:
                    x, y, w, h = mob
                    rotation.rotation(x, y)
                    pickit.pick_it()
                    continue
            except Exception:
                pass

            # 移动
            pather.move_to_ref_location()
            sleep(uniform(0.15, 0.25))

    # === 完整流程 ===

    def run_campaign(self, max_quests: int = 0) -> None:
        """
        自动推进剧情。
        max_quests=0 表示无限循环直到被打断。
        """
        quest_completed = 0

        while max_quests == 0 or quest_completed < max_quests:
            logging_helper.log_info(f"=== Campaign Quest {quest_completed+1} ===")

            # 1. 检查状态
            if self.is_dialogue_active():
                self.handle_dialogue()

            if self.is_cutscene_active():
                self.handle_cutscene()

            if self.is_interaction_prompt():
                self.handle_interaction()

            # 2. 跟随任务标记
            self.follow_quest_marker()

            # 3. 沿途战斗 + 捡东西
            try:
                mob = image_helper.detect_lines('mob')
                if mob:
                    x, y, w, h = mob
                    rotation.rotation(x, y)
                    pickit.pick_it()
            except Exception:
                pass

            # 4. 检测任务是否完成（奖励画面/任务追踪更新）
            # 简化：检测对话/过场触发表明任务推进
            sleep(uniform(0.5, 1.0))
            quest_completed += 1

            # 中断检查
            if self._should_pause():
                break

    def _should_pause(self) -> bool:
        """检查是否应该暂停（虚拟ESC检测）"""
        # 这里可以接入全局暂停信号
        return False


# 便捷函数 — 供 manager.py 调用

def run_campaign_mode(max_quests: int = 0) -> None:
    """便捷入口"""
    runner = CampaignRunner()
    runner.run_campaign(max_quests=max_quests)

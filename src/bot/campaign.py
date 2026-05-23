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
from helper import image_helper
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
        # 对话栏在屏幕底部中央 — 检测白色/浅色文字区域
        w, h = image_helper._detect_screen_size()
        dialogue_x = int(w * 0.15)
        dialogue_y = int(h * 0.78)
        dialogue_w = int(w * 0.70)
        dialogue_h = int(h * 0.08)
        return image_helper.region_match(
            dialogue_x, dialogue_y, dialogue_w, dialogue_h,
            image_helper.is_white_text, min_pct=0.08, cols=10, rows=3)

    def is_cutscene_active(self) -> bool:
        """检测是否在过场动画中"""
        w, h = image_helper._detect_screen_size()

        # 过场：画面上下有黑边，无 HUD
        # 检查顶部黑边
        top_dark = image_helper.region_match(
            0, 0, w, int(h * 0.03),
            image_helper.is_very_dark, min_pct=0.85, cols=10, rows=1)

        # 检查底部黑边
        bottom_dark = image_helper.region_match(
            0, int(h * 0.97), w, int(h * 0.03),
            image_helper.is_very_dark, min_pct=0.85, cols=10, rows=1)

        # 检查技能栏区域 — 过场时技能栏消失
        skill_bar_y = int(h * 0.88)
        skill_bar_h = int(h * 0.10)
        skill_bar_dark = image_helper.region_match(
            0, skill_bar_y, w, skill_bar_h,
            image_helper.is_dark, min_pct=0.70, cols=12, rows=3)

        # 健康球检测 — 过场时无红色健康球
        globe_x = int(w * 0.02)
        globe_y = int(h * 0.87)
        globe_w = int(w * 0.08)
        globe_h = int(h * 0.10)
        has_globe = image_helper.region_match(
            globe_x, globe_y, globe_w, globe_h,
            image_helper.is_reddish, min_pct=0.08, cols=5, rows=3)

        # 过场：黑边 + 无 HUD（无技能栏暗色背景 + 无健康球）
        return (top_dark and bottom_dark) or (skill_bar_dark and not has_globe)

    def is_interaction_prompt(self) -> bool:
        """检测是否有交互提示（"按F交谈"等）"""
        w, h = image_helper._detect_screen_size()
        prompt_x = int(w * 0.35)
        prompt_y = int(h * 0.60)
        prompt_w = int(w * 0.30)
        prompt_h = int(h * 0.10)
        return image_helper.region_match(
            prompt_x, prompt_y, prompt_w, prompt_h,
            image_helper.is_white_text, min_pct=0.05, cols=8, rows=3)

    def has_quest_marker(self) -> bool:
        """
        小地图上是否有任务标记。
        任务标记通常是黄色/金色箭头或红色任务圈。
        """
        w, h = image_helper._detect_screen_size()
        # 小地图在右上角
        map_x = int(w * 0.87)
        map_y = int(h * 0.03)
        map_w = int(w * 0.12)
        map_h = int(h * 0.18)

        has_yellow = image_helper.region_match(
            map_x, map_y, map_w, map_h,
            image_helper.is_yellowish, min_pct=0.03, cols=6, rows=5)

        has_red = image_helper.region_match(
            map_x, map_y, map_w, map_h,
            image_helper.is_reddish, min_pct=0.03, cols=6, rows=5)

        return has_yellow or has_red

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
        w, h = image_helper._detect_screen_size()

        # 持续检测 HUD 恢复
        timeout = 0
        while timeout < 120:  # 最多等2分钟
            # 检测 HUD 是否恢复 — 检查健康球是否出现
            globe_x = int(w * 0.02)
            globe_y = int(h * 0.87)
            globe_w = int(w * 0.08)
            globe_h = int(h * 0.10)
            hud_visible = image_helper.region_match(
                globe_x, globe_y, globe_w, globe_h,
                image_helper.is_reddish, min_pct=0.08, cols=5, rows=3)

            if hud_visible:
                logging_helper.log_info("Cutscene ended")
                self._cutscene_active = False
                return

            # 尝试按 Esc 跳过（部分过场可跳）
            if timeout > 3:
                press('esc')
                sleep(uniform(0.5, 1.0))
                # 检查是否弹出了跳过确认对话框
                center_x = int(w * 0.40)
                center_y = int(h * 0.50)
                center_w = int(w * 0.20)
                center_h = int(h * 0.10)
                has_dialog = image_helper.region_match(
                    center_x, center_y, center_w, center_h,
                    image_helper.is_dark, min_pct=0.50, cols=5, rows=3)
                if has_dialog:
                    leftClick(int(w * 0.5), int(h * 0.55))  # 确认跳过
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

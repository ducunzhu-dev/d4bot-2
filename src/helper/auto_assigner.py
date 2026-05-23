"""
Auto Talent & Paragon Assignment for D4 Paladin S13
Calibrate once (F10 over each node), then fully automatic.
"""
import time
import random
import json
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from typing import List, Tuple, Optional
from pydirectinput import press, leftClick, moveTo

ASSETS_DIR = _ROOT / "assets" / "paladin"
CALIB_FILE = str(ASSETS_DIR / "calibration.json")

# ─── Skill Tree Layout (审判连锁爆炸流) ──────────────────
# Format: (screen_x, screen_y, description)
# These are placeholders - calibrate with F10 on actual game
SKILL_TREE_NODES = [
    # ----- Basic Cluster -----
    (0, 0, "圣光箭 1/5"),
    (0, 0, "圣光箭 2/5"),
    (0, 0, "圣光箭 3/5"),
    (0, 0, "圣光箭 4/5"),
    (0, 0, "圣光箭 5/5"),
    # ----- Core Cluster -----
    (0, 0, "祝福之盾 1/5"),
    (0, 0, "祝福之盾 2/5"),
    (0, 0, "祝福之盾 3/5"),
    (0, 0, "祝福之盾 4/5"),
    (0, 0, "祝福之盾 5/5"),
    # ----- Skill 1: 天堂之矛 -----
    (0, 0, "天堂之矛 1/5"),
    # ----- Skill 2: 圣光光环 -----
    (0, 0, "圣光光环 1/5"),
    # ----- Skill 3: 天罚 -----
    (0, 0, "天罚 1/5"),
    # ----- Skill 4: 审判者誓言 -----
    (0, 0, "审判者誓言 1/1"),
    # ----- Passives -----
    (0, 0, "神圣意志 1/3"),
    (0, 0, "神圣意志 2/3"),
    (0, 0, "神圣意志 3/3"),
    (0, 0, "神圣壁垒 1/3"),
    (0, 0, "神圣壁垒 2/3"),
    (0, 0, "神圣壁垒 3/3"),
    (0, 0, "神圣护体 1/3"),
    (0, 0, "神圣护体 2/3"),
    (0, 0, "神圣护体 3/3"),
    (0, 0, "虔诚回复 1/3"),
    (0, 0, "虔诚回复 2/3"),
    (0, 0, "虔诚回复 3/3"),
    # ----- Extras -----
    (0, 0, "招架训练 1/3"),
    (0, 0, "招架训练 2/3"),
    (0, 0, "招架训练 3/3"),
]

# ─── Paragon Board (审判爆炸流) ──────────────────────
PARAGON_NODES = [
    # Board 1: 神圣壁垒 (格挡+护甲)
    ("board1", 0, 0, "起始节点"),
    ("board1", 0, 0, "雕文槽: 审判"),
    ("board1", 0, 0, "稀有节点: 暴击伤"),
    # Board 2: 仲裁官 (冷却+暴击)
    ("board2", 0, 0, "起始节点"),
    ("board2", 0, 0, "雕文槽: 圣盾"),
    # Board 3: 狂热 (移速+攻速)
    ("board3", 0, 0, "起始节点"),
    ("board3", 0, 0, "雕文槽: 光耀"),
    # Board 4: 虔信 (生命+回复)
    ("board4", 0, 0, "起始节点"),
    ("board4", 0, 0, "雕文槽: 惩戒"),
]


class AutoAssigner:
    """Automated talent + paragon assignment."""

    def __init__(self):
        self.calibration = self._load_calibration()

    def _load_calibration(self) -> dict:
        try:
            with open(CALIB_FILE) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def save_calibration(self, name: str, x: int, y: int):
        """Save a calibration point."""
        self.calibration[name] = {'x': x, 'y': y}
        Path(CALIB_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(CALIB_FILE, 'w') as f:
            json.dump(self.calibration, f, indent=2, ensure_ascii=False)

    def auto_assign_skills(self) -> bool:
        """Auto-assign all skill points using calibrated positions."""
        if not self.calibration:
            print("[AutoAssign] No calibration data. Run calibration first.")
            return False

        # Open skill tree
        press('s')
        time.sleep(random.uniform(0.6, 0.9))

        assigned = 0
        for x, y, desc in SKILL_TREE_NODES:
            # Check if we have calibrated position
            key = f"skill:{desc}"
            pos = self.calibration.get(key)
            if pos:
                self._click_node(pos['x'], pos['y'])
                assigned += 1
                time.sleep(random.uniform(0.08, 0.15))

        # Close skill tree
        press('s')
        print(f"[AutoAssign] Skill points: {assigned} nodes clicked")
        return assigned > 0

    def auto_assign_paragon(self) -> bool:
        """Auto-assign paragon points."""
        if not self.calibration:
            return False

        # Open paragon
        press('p')
        time.sleep(random.uniform(0.6, 0.9))

        assigned = 0
        current_board = None
        for board, x, y, desc in PARAGON_NODES:
            pos = self.calibration.get(f"paragon:{desc}")
            if pos:
                if board != current_board:
                    # Switch paragon board (click board tab or rotate)
                    self._switch_paragon_board(board)
                    current_board = board
                    time.sleep(random.uniform(0.3, 0.5))
                self._click_node(pos['x'], pos['y'])
                assigned += 1
                time.sleep(random.uniform(0.08, 0.15))

        press('p')
        print(f"[AutoAssign] Paragon points: {assigned} nodes")
        return assigned > 0

    def _click_node(self, x: int, y: int):
        """Click a skill tree / paragon node."""
        # Add slight jitter
        jx = x + random.randint(-2, 2)
        jy = y + random.randint(-2, 2)
        moveTo(jx, jy)
        time.sleep(random.uniform(0.03, 0.06))
        leftClick(jx, jy)

    def _switch_paragon_board(self, board_name: str):
        """Switch to a different paragon board (rotate gate)."""
        # Gate rotation is at a fixed position - needs calibration
        gate_pos = self.calibration.get(f"paragon:gate_{board_name}")
        if gate_pos:
            leftClick(gate_pos['x'], gate_pos['y'])
            time.sleep(random.uniform(0.3, 0.5))

    def run_calibration_guide(self):
        """Print calibration instructions for Jonathan."""
        print("=" * 50)
        print("  CALIBRATION MODE")
        print("=" * 50)
        print()
        print("1. Open game (1920x1080 windowed fullscreen)")
        print("2. Press S to open skill tree")
        print("3. Hover mouse over first skill node")
        print("4. Press F10 to record coordinates")
        print("5. Tell me: '<skill_name> at <x>, <y>'")
        print("6. Repeat for all skills and paragon nodes")
        print()
        print("Nodes to calibrate (in order):")
        for x, y, desc in SKILL_TREE_NODES:
            print(f"  - {desc}")
        print()
        print("Paragon nodes:")
        for board, x, y, desc in PARAGON_NODES:
            print(f"  - [{board}] {desc}")


if __name__ == "__main__":
    aa = AutoAssigner()
    aa.run_calibration_guide()

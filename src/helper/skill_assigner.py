"""
Auto Skill Assignment for D4 Paladin S13
Opens skill tree and drags skills to bar using pixel detection.
"""
import time
import random
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
from typing import Tuple, Optional

from pydirectinput import press, leftClick, moveTo, keyDown, keyUp
from helper import image_helper, mouse_helper, logging_helper

ASSETS = _ROOT / "assets"
SKILL_TREE_IMG = str(ASSETS / "skills" / "paladin")

# Skill tree button positions (1920x1080, windowed fullscreen)
# These are approximate - fine-tune with F10 toolbox if needed
SKILL_TREE_BTN = (1750, 100)    # Skill tree tab button (right side)
SKILL_SLOTS = {
    'left':  (350, 980),   # Left click slot
    'right': (550, 980),   # Right click slot
    '1':     (750, 980),   # Skill 1
    '2':     (850, 980),   # Skill 2
    '3':     (950, 980),   # Skill 3
    '4':     (1050, 980),  # Skill 4
}

# Assign skills by opening skill tree and clicking each node
# Skills are found by template matching in the tree
SKILLS_TO_ASSIGN = [
    {'name': '圣光箭', 'file': 'holy_arrow.png', 'slot': 'left'},
    {'name': '祝福之盾', 'file': 'blessed_shield.png', 'slot': 'right'},
    {'name': '天堂之矛', 'file': 'heaven_spear.png', 'slot': '1'},
    {'name': '圣光光环', 'file': 'holy_aura.png', 'slot': '2'},
    {'name': '天罚', 'file': 'divine_punish.png', 'slot': '3'},
    {'name': '审判者誓言', 'file': 'judicator_vow.png', 'slot': '4'},
]


def assign_all_skills() -> bool:
    """
    Auto-assign all 6 skills to the skill bar.
    Opens skill tree, finds each skill by template matching, clicks to assign.
    Returns True if all skills assigned successfully.
    """
    logging_helper.log_info("[AutoAssign] Starting skill assignment...")

    # Open skill tree
    press('s')
    time.sleep(random.uniform(0.5, 0.8))

    assigned = 0
    for skill in SKILLS_TO_ASSIGN:
        success = assign_single_skill(skill['file'], skill['slot'])
        if success:
            assigned += 1
            logging_helper.log_info(f"[AutoAssign] {skill['name']} → {skill['slot']} OK")
        else:
            logging_helper.log_error(f"[AutoAssign] {skill['name']} FAILED")
        time.sleep(random.uniform(0.3, 0.6))

    # Close skill tree
    press('s')
    time.sleep(random.uniform(0.3, 0.5))

    logging_helper.log_info(f"[AutoAssign] Done: {assigned}/{len(SKILLS_TO_ASSIGN)} assigned")
    return assigned == len(SKILLS_TO_ASSIGN)


def assign_single_skill(skill_img: str, slot: str) -> bool:
    """
    Find a skill in the open skill tree and assign to a bar slot.
    Uses template matching to locate the skill icon in the tree,
    then clicks it and assigns to the slot.
    """
    try:
        skill_path = str(Path(SKILL_TREE_IMG) / skill_img)

        # Try to find the skill icon in the skill tree area
        # Tree area is roughly the right 2/3 of the screen
        tree_region = (300, 100, 1500, 800)
        result = image_helper.locate_needle(skill_path, conf=0.6, loctype='c', region=tree_region)

        if not result or (result[0] == -1 and result[1] == -1):
            # Try scrolling the tree and searching again
            _scroll_tree()
            time.sleep(random.uniform(0.3, 0.5))
            result = image_helper.locate_needle(skill_path, conf=0.6, loctype='c', region=tree_region)

        if not result or (result[0] == -1 and result[1] == -1):
            logging_helper.log_debug(f"Skill icon {skill_img} not found in tree")
            return False

        # Click the skill in the tree
        x, y = _get_result_center(result)
        mouse_helper.move_smooth(x, y, duration=0.2)
        time.sleep(random.uniform(0.1, 0.2))
        leftClick(x, y)

        # Small delay for assignment UI
        time.sleep(random.uniform(0.5, 0.7))

        # Click the target slot to assign
        slot_pos = SKILL_SLOTS.get(slot)
        if slot_pos:
            mouse_helper.move_smooth(slot_pos[0], slot_pos[1], duration=0.15)
            time.sleep(random.uniform(0.1, 0.15))
            leftClick(slot_pos[0], slot_pos[1])
            time.sleep(random.uniform(0.2, 0.3))

        return True

    except Exception as ex:
        logging_helper.log_debug(f"assign_single_skill error: {ex}")
        return False


def _get_result_center(result) -> Tuple[int, int]:
    """Extract center coordinates from locate_needle result."""
    if hasattr(result, 'x') and hasattr(result, 'y'):
        if hasattr(result, 'width'):
            return int(result.x + result.width / 2), int(result.y + result.height / 2)
        return int(result.x + 25), int(result.y + 25)
    if isinstance(result, (tuple, list)) and len(result) >= 2:
        return int(result[0] + 25), int(result[1] + 25)
    return 500, 500


def _scroll_tree():
    """Scroll the skill tree view."""
    for _ in range(3):
        mouse_helper.mouseScroll(-2)
        time.sleep(random.uniform(0.1, 0.2))


# ─── Quick setup via keyboard shortcuts (no image matching needed) ───

def quick_assign_via_clicks():
    """
    Alternative: assign skills by clicking skill tree nodes at known positions.
    Requires running once with F10 to calibrate positions.
    Call after opening skill tree (press 'S').
    """
    # This is a calibration-based approach - positions need to be set
    # after running F10 calibration on the actual game
    logging_helper.log_info("[QuickAssign] Starting position-based assignment...")
    # To be calibrated with F10 toolbox
    pass


if __name__ == "__main__":
    print("Auto Skill Assignment Module")
    print("Run assign_all_skills() from the bot main loop to auto-assign.")
    print("Skills will be assigned using template matching on skill icons.")

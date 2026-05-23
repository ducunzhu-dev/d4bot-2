"""
背包管理模块 — 自动筛选/分解/存仓/提取威能
基于像素检测 + 物品悬浮信息读取
集成 D4LF TTS 方案（可选）或纯图像 OCR fallback
支持自动校准坐标
"""
from time import sleep
from random import uniform, randint
from typing import Optional, Tuple, List
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]
import yaml

from pydirectinput import leftClick, rightClick, press
from helper import mouse_helper, image_helper, config_helper, logging_helper
from bot import calibration_loader as cal

# 路径
ASSETS_DIR = _ROOT / "assets"
CONFIG_DIR = _ROOT / "config"

# === 自动校准坐标（优先 calibration.yaml，回退硬编码）===
def _get_first_slot():
    inv = cal.get_ui('inventory', {})
    fs = inv.get('first_slot', {'x': 1420, 'y': 420})
    return (fs['x'], fs['y'])

def _get_slot_size():
    inv = cal.get_ui('inventory', {})
    sz = inv.get('slot_size', {'width': 55, 'height': 55})
    return (sz['width'], sz['height'])

INV_FIRST_SLOT = _get_first_slot()
INV_SLOT_WIDTH, INV_SLOT_HEIGHT = _get_slot_size()
INV_COLS = 3
INV_ROWS = 11
INV_MAX_SLOTS = 33

# NPC 坐标（优先校准值）
def _get_npc_pos(npc_type):
    npcs = cal.get_ui('npc_approx', {})
    pos = npcs.get(npc_type, {})
    return (pos.get('x', 400), pos.get('y', 500))

BLACKSMITH_POS = _get_npc_pos('blacksmith')
STASH_POS = _get_npc_pos('stash')
OCCULTIST_POS = _get_npc_pos('occultist')

# 城镇传送点（Kyovashad 默认）
TOWN_WAYPOINT = (image_helper.scale_x(960), image_helper.scale_y(540))

# 颜色配置
COLOR_LEGENDARY = (255, 140, 0)    # 传奇金色
COLOR_UNIQUE = (210, 150, 100)     # 独特褐色
COLOR_RARE = (255, 255, 0)         # 稀有黄色
COLOR_MAGIC = (100, 100, 255)      # 魔法蓝色
COLOR_NORMAL = (180, 180, 180)     # 普通灰色


class InventoryManager:
    """背包自动化管理"""

    def __init__(self):
        self.cfg = config_helper.read_config() or {}
        self.class_name = self.cfg.get('class', 'barbarian').lower()
        self.aspects_config = self._load_aspects()
        self.glyphs_config = self._load_glyphs()
        self._inventory_state = {}  # 背包状态缓存 {slot: item_info}

    def _load_aspects(self) -> dict:
        """加载当前职业的威能词典"""
        path = CONFIG_DIR / f"aspects_{self.class_name}.yaml"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            logging_helper.log_debug(f"Failed to load aspects config: {path}")
            return {}

    def _load_glyphs(self) -> dict:
        """加载雕文优先序"""
        path = CONFIG_DIR / "glyphs.yaml"
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}

    # === 状态检测 ===

    def is_inventory_open(self) -> bool:
        """检测背包是否打开（背包面板覆盖屏幕中央）"""
        w, h = image_helper._detect_screen_size()
        # 背包面板在屏幕中央偏右，有深色半透明背景
        inv_x = int(w * 0.55)
        inv_y = int(h * 0.15)
        inv_w = int(w * 0.40)
        inv_h = int(h * 0.70)
        return image_helper.region_match(
            inv_x, inv_y, inv_w, inv_h,
            image_helper.is_dark, min_pct=0.55, cols=8, rows=10)

    def is_inventory_full(self) -> bool:
        """检测背包是否满了（屏幕中央红色提示文字）"""
        w, h = image_helper._detect_screen_size()
        alert_x = int(w * 0.35)
        alert_y = int(h * 0.25)
        alert_w = int(w * 0.30)
        alert_h = int(h * 0.08)
        return image_helper.region_match(
            alert_x, alert_y, alert_w, alert_h,
            image_helper.is_reddish, min_pct=0.05, cols=8, rows=3)

    def is_salvage_window_open(self) -> bool:
        """检测是否在铁匠分解界面"""
        w, h = image_helper._detect_screen_size()
        # 铁匠界面在屏幕左侧，有橙色/红色 UI 元素
        salvage_x = int(w * 0.05)
        salvage_y = int(h * 0.15)
        salvage_w = int(w * 0.25)
        salvage_h = int(h * 0.30)
        return image_helper.region_match(
            salvage_x, salvage_y, salvage_w, salvage_h,
            image_helper.is_orange, min_pct=0.04, cols=6, rows=5)

    # === 物品识别 ===

    def get_item_rarity(self, x: int, y: int) -> str:
        """通过物品槽位区域颜色判断稀有度"""
        # 采样物品图标周围的小区域
        samples = image_helper.sample_region(
            int(x) - 5, int(y) - 5, 55, 25, 5, 3)
        if not samples:
            return 'normal'

        for r, g, b in samples:
            s = r + g + b
            if s < 30:
                continue
            # 传奇: 橙色/金色
            if image_helper.is_orange(r, g, b):
                return 'legendary'
            # 独特: 棕色
            if r > 140 and g > 80 and r > g and r > b and s < 500:
                return 'unique'

        # 检查主颜色
        for r, g, b in samples:
            s = r + g + b
            if s < 30:
                continue
            if image_helper.is_yellowish(r, g, b):
                return 'rare'
            if image_helper.is_blueish(r, g, b):
                return 'magic'

        return 'normal'

    def read_item_tooltip(self, x: int, y: int) -> Optional[dict]:
        """
        悬浮物品读取 tooltip。
        尝试 TTS hook 方案，fallback 到图像 OCR。
        返回 {'name': str, 'rarity': str, 'item_power': int, 'affixes': list, 'aspect': str}
        """
        # 移动鼠标到物品槽位
        mouse_helper.move_smooth(x + 25, y + 25, 1)
        sleep(uniform(0.15, 0.25))

        # TODO: TTS hook 方案 — 拦截 D4 accessibility API
        # 当前简化为纯像素判断 + 配置查表
        rarity = self.get_item_rarity(x, y)

        return {
            'rarity': rarity,
            'name': 'unknown',
            'item_power': 0,
            'affixes': [],
            'aspect': None,
        }

    # === 决策逻辑 ===

    def should_keep_item(self, item: dict) -> Tuple[str, str]:
        """
        判断物品处理方式。
        返回 (action, reason)
        action: 'keep' | 'salvage' | 'extract_aspect' | 'equip'
        """
        rarity = item.get('rarity', 'normal')
        aspect_name = item.get('aspect')
        affixes = item.get('affixes', [])

        # 独特装备 — 始终保留
        if rarity == 'unique':
            return 'keep', '独特装备必留'

        # 传奇装备 — 检查威能评分
        if rarity == 'legendary':
            aspects = self.aspects_config.get('aspects', {})
            score = aspects.get(aspect_name, 50)  # 未知威能默认50分

            if score >= 85:
                return ('equip', f'S级威能 {aspect_name}({score}分)')
            elif score >= 70:
                return ('keep', f'A级威能 {aspect_name}({score}分)')
            elif aspect_name and score < 70:
                return ('extract_aspect', f'提取威能 {aspect_name}({score}分)')
            else:
                return ('keep', f'未识别威能，默认保留')

        # 稀有装备 — 检查词缀
        if rarity == 'rare':
            priority_affixes = self.aspects_config.get('affix_priority', [])
            matched = 0
            for affix in affixes:
                for p in priority_affixes:
                    if p.lower() in affix.lower():
                        matched += 1
                        break
            if matched >= 2:
                return ('keep', f'稀有装备匹配{matched}个偏好词缀')

        # 魔法/普通 — 分解
        return ('salvage', f'{rarity}品质自动分解')

    # === 自动化操作 ===

    def open_inventory(self, max_attempts: int = 3) -> bool:
        """打开背包，带重试"""
        for _ in range(max_attempts):
            press('i')
            sleep(uniform(0.3, 0.5))
            if self.is_inventory_open():
                return True
        logging_helper.log_error("Failed to open inventory")
        return False

    def scan_inventory(self) -> List[dict]:
        """扫描背包所有槽位，返回物品列表"""
        items = []
        for row in range(INV_ROWS):
            for col in range(INV_COLS):
                slot_x = INV_FIRST_SLOT[0] + col * INV_SLOT_WIDTH
                slot_y = INV_FIRST_SLOT[1] + row * INV_SLOT_HEIGHT
                item = self.read_item_tooltip(slot_x, slot_y)
                if item and item.get('rarity') != 'empty':
                    item['slot'] = (slot_x, slot_y)
                    item['row'] = row
                    item['col'] = col
                    items.append(item)
        logging_helper.log_info(f"Scanned {len(items)} items in inventory")
        return items

    def salvage_all_junk(self, junk_items: List[dict]) -> None:
        """去铁匠分解垃圾"""
        if not junk_items:
            return

        # 1. 传送到城镇
        self._teleport_to_town()

        # 2. 走到铁匠
        self._walk_to_npc('blacksmith')

        # 3. 打开分解界面
        press('f')  # 交互键
        sleep(uniform(0.5, 0.8))

        # 4. 标记垃圾（需要游戏内标记功能，简化版：逐个分解）
        for item in junk_items:
            slot = item.get('slot', (0, 0))
            leftClick(slot[0] + 25, slot[1] + 25)
            sleep(uniform(0.1, 0.2))
            press('space')  # D4 默认分解键
            sleep(uniform(0.15, 0.25))

        # 5. 退出
        press('esc')
        sleep(uniform(0.3, 0.5))

    def deposit_keepers(self, keeper_items: List[dict]) -> None:
        """把保留物品存入仓库"""
        if not keeper_items:
            return

        self._walk_to_npc('stash')
        press('f')
        sleep(uniform(0.5, 0.8))

        for item in keeper_items:
            # 右键物品 → 自动存入仓库（D4 默认行为）
            slot = item.get('slot', (0, 0))
            rightClick(slot[0] + 25, slot[1] + 25)
            sleep(uniform(0.1, 0.15))

        press('esc')
        sleep(uniform(0.3, 0.5))

    def extract_aspects(self, extract_items: List[dict]) -> None:
        """去秘术师提取威能"""
        if not extract_items:
            return

        self._walk_to_npc('occultist')
        press('f')
        sleep(uniform(0.5, 0.8))

        # 选择提取标签页（像素检测"提取威能"按钮）
        # 简化版：默认在提取界面
        for item in extract_items:
            slot = item.get('slot', (0, 0))
            leftClick(slot[0] + 25, slot[1] + 25)
            sleep(uniform(0.1, 0.2))
            # 点击提取按钮（坐标需模板匹配）
            leftClick(image_helper.scale_x(960), image_helper.scale_y(700))
            sleep(uniform(0.3, 0.5))

        press('esc')

    # === 完整流程 ===

    def run_inventory_cycle(self) -> None:
        """
        完整背包管理周期：
        打开背包 → 扫描 → 决策 → 分解 → 存仓 → 提取威能
        """
        logging_helper.log_info("=== Starting inventory management cycle ===")

        if not self.open_inventory():
            logging_helper.log_error("Cannot open inventory, skipping cycle")
            return

        items = self.scan_inventory()

        junk = []
        keepers = []
        extract = []

        for item in items:
            action, reason = self.should_keep_item(item)
            logging_helper.log_info(f"Item {item.get('name','?')}: {action} — {reason}")

            if action == 'salvage':
                junk.append(item)
            elif action == 'extract_aspect':
                extract.append(item)
            else:
                keepers.append(item)

        press('esc')  # 关闭背包
        sleep(uniform(0.3, 0.5))

        # 执行分解
        if junk:
            logging_helper.log_info(f"Salvaging {len(junk)} items")
            self.salvage_all_junk(junk)

        # 提取威能
        if extract:
            logging_helper.log_info(f"Extracting aspects from {len(extract)} items")
            self.extract_aspects(extract)

        # 存仓库
        if keepers:
            logging_helper.log_info(f"Depositing {len(keepers)} items to stash")
            self.deposit_keepers(keepers)

        logging_helper.log_info("=== Inventory management cycle complete ===")

    # === 辅助方法 ===

    def _teleport_to_town(self) -> None:
        """传送到城镇"""
        press('t')  # D4 默认回城
        sleep(uniform(3.0, 5.0))  # 等加载

    def _walk_to_npc(self, npc_type: str) -> None:
        """
        走到指定 NPC。
        简化版：点击小地图大致位置 + 短暂等待。
        完整版需要模板匹配精确定位。
        """
        npc_positions = {
            'blacksmith': (image_helper.scale_x(300), image_helper.scale_y(700)),
            'stash': (image_helper.scale_x(200), image_helper.scale_y(600)),
            'occultist': (image_helper.scale_x(350), image_helper.scale_y(650)),
        }
        target = npc_positions.get(npc_type, (image_helper.scale_x(400), image_helper.scale_y(500)))
        # 点击小地图位置（由主模块 manager 调用 pather 处理）
        leftClick(target[0], target[1])
        sleep(uniform(1.0, 1.5))

    def mark_all_salvage(self) -> None:
        """批量标记背包物品为垃圾（需要先打开背包）"""
        # D4 快捷键：标记垃圾
        # 切换标记模式 → 遍历所有格子
        for row in range(INV_ROWS):
            for col in range(INV_COLS):
                slot_x = INV_FIRST_SLOT[0] + col * INV_SLOT_WIDTH
                slot_y = INV_FIRST_SLOT[1] + row * INV_SLOT_HEIGHT
                leftClick(slot_x + randint(-5, 5), slot_y + randint(-3, 3))
                sleep(uniform(0.02, 0.05))
                press('space')  # 标记为垃圾


# 便捷函数 — 供 manager.py 调用

_inv_mgr_instance = None

def check_and_manage_inventory() -> bool:
    """
    检查背包状态，满则执行管理。
    返回 True 表示执行了管理，False 表示跳过。
    """
    global _inv_mgr_instance
    if _inv_mgr_instance is None:
        _inv_mgr_instance = InventoryManager()
    inv_mgr = _inv_mgr_instance
    if inv_mgr.is_inventory_full():
        inv_mgr.run_inventory_cycle()
        return True
    return False


if __name__ == "__main__":
    # 独立测试
    mgr = InventoryManager()
    print(f"Class: {mgr.class_name}")
    print(f"Aspects loaded: {len(mgr.aspects_config.get('aspects', {}))} entries")
    print(f"Affix priority: {mgr.aspects_config.get('affix_priority', [])[:5]}...")

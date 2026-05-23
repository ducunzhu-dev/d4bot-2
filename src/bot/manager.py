from time import sleep
from random import randint, uniform
from typing import Optional, Tuple
from pathlib import Path
import sys

_ROOT = Path(sys._MEIPASS) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]

from pydirectinput import leftClick, rightClick, press

from helper import mouse_helper, image_helper, config_helper, logging_helper
from bot import pather, pickit, rotation, inventory, dungeon, campaign

ASSETS_DIR = _ROOT / "assets"
LOCATION_DIR = str(ASSETS_DIR / "location")

# Resolutions-Skalierung
from helper.image_helper import scale_x, scale_y, scale_region

class Manager:
    def __init__(self) -> None:
        # Config beim Start laden; bei Bedarf kann reload_config() verwendet werden
        self.cfg = self.reload_config()

    def reload_config(self):
        try:
            return config_helper.read_config() or {}
        except Exception as ex:
            logging_helper.log_debug("Failed to read config: %s" % ex)
            return {}

    def _safe_locate(self, path: str, **kwargs) -> Tuple[int, int]:
        """
        Wrapper fuer image_helper.locate_needle, der ein konsistentes (-1, -1) zurueckgibt bei Fehlern.
        """
        try:
            res = image_helper.locate_needle(path, **kwargs)
            if res is True:
                return 0, 0
            if not res or res is False:
                return -1, -1
            if hasattr(res, 'x') and hasattr(res, 'y'):
                return int(res.x), int(res.y)
            if isinstance(res, (tuple, list)) and len(res) >= 2:
                if res[0] is None or res[1] is None:
                    return -1, -1
                return int(res[0]), int(res[1])
            return -1, -1
        except Exception as ex:
            logging_helper.log_debug("locate_needle error for %s: %s" % (path, ex))
            return -1, -1

    def is_on_landing(self) -> bool:
        """Landing/character select screen — medium brightness, no skill bar."""
        try:
            w, h = image_helper._detect_screen_size()
            # Sample full screen — landing screen has varied brightness
            samples = image_helper.sample_region(0, 0, w, h, 8, 6)
            if not samples:
                return False

            def is_medium(r, g, b):
                avg = (r + g + b) / 3
                return 15 < avg < 220

            medium_pct = sum(1 for s in samples if is_medium(*s)) / len(samples)
            return 0.40 <= medium_pct <= 0.90
        except Exception as ex:
            logging_helper.log_debug("is_on_landing error: %s" % ex)
            return False

    def is_on_menu(self) -> bool:
        """
        D4 main menu: dark background with character model and UI buttons.
        Key indicators:
        - NO red health globe (definitive: not in-game)
        - Screen is predominantly dark (60-92% dark pixels)
        - Some bright UI elements (buttons, logo)
        """
        try:
            w, h = image_helper._detect_screen_size()

            # 1. Health globe area: must NOT show red (rules out in-game)
            globe_x = int(w * 0.02)
            globe_y = int(h * 0.87)
            globe_w = int(w * 0.09)
            globe_h = int(h * 0.10)
            has_globe = image_helper.region_match(
                globe_x, globe_y, globe_w, globe_h,
                image_helper.is_reddish, min_pct=0.10, cols=5, rows=4)
            if has_globe:
                return False  # Red globe visible → in-game, not menu

            # 2. Sample full screen — menu is mostly dark but not all-black
            samples = image_helper.sample_region(0, 0, w, h, 10, 8)
            if not samples:
                return False
            dark_pct = sum(1 for r, g, b in samples
                          if image_helper.is_dark(r, g, b)) / len(samples)

            # Menu: 55-93% dark pixels (loading would be >95%)
            return 0.55 <= dark_pct <= 0.93
        except Exception as ex:
            logging_helper.log_debug("is_on_menu error: %s" % ex)
            return False

    def is_on_loading(self) -> bool:
        """
        Loading screen: nearly entire screen is black.
        D4 loading screen is pitch black with a small logo.
        """
        try:
            w, h = image_helper._detect_screen_size()

            # Sample full screen — loading should be >95% near-black
            samples = image_helper.sample_region(0, 0, w, h, 10, 8)
            if not samples:
                # Fallback: if we can't grab screen, assume NOT loading
                return False

            very_dark_pct = sum(1 for r, g, b in samples
                               if image_helper.is_very_dark(r, g, b)) / len(samples)
            return very_dark_pct >= 0.94
        except Exception as ex:
            logging_helper.log_debug("is_on_loading error: %s" % ex)
            return False

    def is_in_game(self) -> bool:
        """
        In-game: skill bar visible with red health globe at bottom-left.
        This is the most reliable D4 in-game indicator across all resolutions.
        The health globe is a distinctive crimson-red UI element that doesn't
        exist on any other screen (menu, loading, death).
        """
        try:
            w, h = image_helper._detect_screen_size()

            # 1. Health globe: bottom-left corner, red orb UI
            globe_x = int(w * 0.02)
            globe_y = int(h * 0.87)
            globe_w = int(w * 0.09)
            globe_h = int(h * 0.10)
            has_globe = image_helper.region_match(
                globe_x, globe_y, globe_w, globe_h,
                image_helper.is_reddish, min_pct=0.12, cols=6, rows=5)

            if not has_globe:
                return False

            # 2. Game world: center of screen should have visible content
            world_x = int(w * 0.15)
            world_y = int(h * 0.10)
            world_w = int(w * 0.70)
            world_h = int(h * 0.72)
            world_visible = image_helper.region_match(
                world_x, world_y, world_w, world_h,
                image_helper.is_visible, min_pct=0.45, cols=8, rows=6)

            return world_visible
        except Exception as ex:
            logging_helper.log_debug("is_in_game error: %s" % ex)
            return False

    def is_dead(self) -> bool:
        """
        Death screen: world is desaturated (ghost filter) + revive UI at bottom.
        Secondary check: health globe area is NOT red (empty/dark).
        """
        try:
            w, h = image_helper._detect_screen_size()

            # 1. Quick sanity: NOT loading (loading is all-black)
            loading_samples = image_helper.sample_region(0, 0, w, h, 5, 4)
            if loading_samples:
                black_pct = sum(1 for r, g, b in loading_samples
                               if image_helper.is_very_dark(r, g, b)) / len(loading_samples)
                if black_pct > 0.85:
                    return False  # Loading, not death

            # 2. Health globe area: should NOT show normal red
            globe_x = int(w * 0.02)
            globe_y = int(h * 0.87)
            globe_w = int(w * 0.09)
            globe_h = int(h * 0.10)
            globe_red = image_helper.region_match(
                globe_x, globe_y, globe_w, globe_h,
                image_helper.is_reddish, min_pct=0.08, cols=5, rows=4)
            if globe_red:
                return False  # Normal health visible → not dead

            # 3. Revive button area at bottom-center
            revive_x = int(w * 0.30)
            revive_y = int(h * 0.90)
            revive_w = int(w * 0.40)
            revive_h = int(h * 0.07)
            has_revive_ui = image_helper.region_match(
                revive_x, revive_y, revive_w, revive_h,
                image_helper.is_bright, min_pct=0.12, cols=8, rows=3)

            # 4. Game world desaturation (death ghost filter)
            world_x = int(w * 0.20)
            world_y = int(h * 0.20)
            world_w = int(w * 0.60)
            world_h = int(h * 0.55)
            world_desat = image_helper.region_match(
                world_x, world_y, world_w, world_h,
                image_helper.is_desaturated, min_pct=0.35, cols=7, rows=5)

            return has_revive_ui and world_desat
        except Exception as ex:
            logging_helper.log_debug("is_dead error: %s" % ex)
            return False

    def click_randomized(self, x: Optional[int] = None, y: Optional[int] = None,
                         jitter: Tuple[int, int, int, int] = (-5, 35, -5, 5), button: str = 'left') -> None:
        """Perform a randomized click action."""
        try:
            if x is None or y is None:
                if button == 'left':
                    leftClick()
                else:
                    rightClick()
                logging_helper.log_debug("Clicked at current cursor position (%s)" % button)
                return

            ex = randint(jitter[0], jitter[1])
            ey = randint(jitter[2], jitter[3])
            fx, fy = int(x + ex), int(y + ey)

            if button == 'left':
                leftClick(fx, fy)
            else:
                rightClick(fx, fy)

            logging_helper.log_debug("Clicked randomized at %d,%d (base %d,%d) button=%s" % (fx, fy, x, y, button))
        except Exception as ex:
            logging_helper.log_debug("click_randomized failed: %s" % ex)

    def key_press(self, key: str) -> None:
        try:
            press(key)
            logging_helper.log_debug("Pressed key: %s" % key)
        except Exception as ex:
            logging_helper.log_debug("key_press failed for %s: %s" % (key, ex))

    def wait_and_retry(self, condition_func, max_attempts: int = 10, delay: float = 0.5) -> bool:
        """Wait for a condition to be met with retries."""
        for attempt in range(max_attempts):
            try:
                if condition_func():
                    return True
            except Exception as ex:
                logging_helper.log_debug("wait_and_retry condition error: %s" % ex)
                return False
            sleep(delay)
        return False

    def loot_process(self, attempts: int = 30) -> None:
        """Versucht mehrere Male Loot aufzunehmen (non-blocking)."""
        for _ in range(attempts):
            try:
                if not pickit.pick_it():
                    break
                # leichte Pause zwischen erfolgreichen Picks
                sleep(uniform(0.2, 0.4))
            except Exception as ex:
                logging_helper.log_debug("loot_process error: %s" % ex)
                break

    def wait_for_loading(self) -> None:
        if not self.wait_and_retry(self.is_on_loading, delay=0.5):
            sleep(uniform(1.5, 2.5))

    def navigate_to_treasure(self) -> None:
        logging_helper.log_info("Attempting to locate treasure.")
        try:
            self.key_press('TAB')
            sleep(uniform(0.5, 0.8))
            mouse_helper.move_smooth(800, 600)
            sleep(uniform(0.5, 0.8))

            # Scroll to adjust the view
            for _ in range(4):
                mouse_helper.mouseScroll(-1)
                sleep(uniform(0.2, 0.4))
            for _ in range(3):
                mouse_helper.mouseScroll(1)
                sleep(uniform(0.2, 0.4))

            screen_region = scale_region((50, 50, 1900, 870))
            x, y = self._safe_locate(str(Path(LOCATION_DIR) / "treasure.png"),
                                     conf=0.8, loctype='c', region=screen_region)

            if x != -1 and y != -1:
                self.click_randomized(x, y, button='right')
                logging_helper.log_info("Found armor treasure at map position %d, %d." % (x, y))
                return

            logging_helper.log_info("Treasure not found; attempting fallback locations.")
            self.fallback_navigation(screen_region)
        except Exception as ex:
            logging_helper.log_debug("navigate_to_treasure error: %s" % ex)

    def fallback_navigation(self, region: Tuple[int, int, int, int]) -> Optional[bool]:
        try:
            if self._safe_locate(str(Path(LOCATION_DIR) / "onyxWatchtower.png"), conf=0.8, region=region)[0] != -1:
                self.key_press('m')
                return True
            if self._safe_locate(str(Path(LOCATION_DIR) / "rakhatKeep.png"), conf=0.8, region=region)[0] != -1:
                # Scaled fallback: rahkat keep teleport
                self.click_randomized(scale_x(1097), scale_y(764), button='right')
                return True
            return self.search_helltide(region)
        except Exception as ex:
            logging_helper.log_debug("fallback_navigation error: %s" % ex)
            return None

    def search_helltide(self, region: Tuple[int, int, int, int]) -> Optional[bool]:
        try:
            for _ in range(3):
                mouse_helper.mouseScroll(-1)
                sleep(uniform(0.2, 0.4))

            x, y = self._safe_locate(str(Path(LOCATION_DIR) / "helltide.png"),
                                     conf=0.8, loctype='c', region=region)
            if x == -1:
                return None

            left = max(x - 25, 0)
            top = max(y - 75, 0)
            waypoint_region = (left, top, 50, 100)
            x2, y2 = self._safe_locate(str(Path(LOCATION_DIR) / "waypoint.png"),
                                      conf=0.8, loctype='c', region=waypoint_region)

            if x2 != -1 and y2 != -1:
                self.click_randomized(x2, y2, jitter=(1, 4, 1, 4), button='left')
                logging_helper.log_info("Found helltide waypoint at %d, %d. Teleporting." % (x2, y2))
                # Teleport action: sichere Klickkoordinate
                self.click_randomized(scale_x(850), scale_y(640), button='left')
                return True

            # close map to continue if nothing found
            self.key_press('m')
            return None
        except Exception as ex:
            logging_helper.log_debug("search_helltide error: %s" % ex)
            return None

    def game_manager(self, move: bool = True, loot: bool = False) -> None:
        """Main game handling routine — with mode switching and inventory management."""
        try:
            # Aktualisiere ggf. die Konfiguration
            self.cfg = self.reload_config()

            # === 模式切换 ===
            mode = self.cfg.get('mode', 'helltide')  # helltide / nmd / campaign
            cls = self.cfg.get('class', '?')
            logging_helper.log_info(f"game_manager tick: class={cls} mode={mode}")

            if self.is_on_menu():
                logging_helper.log_info("Player is on menu. Starting game.")
                self.click_randomized(scale_x(220), scale_y(710), button='left')
                return

            if self.is_dead():
                logging_helper.log_info("Player is dead. Reviving.")
                self.click_randomized(scale_x(927), scale_y(948), button='left')
                self.wait_for_loading()
                return

            # === 背包管理检查 ===
            try:
                inventory.check_and_manage_inventory()
            except Exception as ex:
                logging_helper.log_debug("inventory check error: %s" % ex)

            if self.is_in_game():
                # === 模式路由 ===
                if mode == 'campaign':
                    logging_helper.log_info("Mode: Campaign")
                    try:
                        campaign.run_campaign_mode(max_quests=0)
                    except Exception as ex:
                        logging_helper.log_debug("campaign error: %s" % ex)
                    return

                if mode == 'nmd':
                    logging_helper.log_info("Mode: Nightmare Dungeon")
                    try:
                        dungeon.run_nightmare_dungeon(max_runs=1)
                    except Exception as ex:
                        logging_helper.log_debug("dungeon error: %s" % ex)
                    return

                # === 默认: Helltide 模式 ===
                logging_helper.log_info("Player is in-game.")
                try:
                    mob = image_helper.detect_lines('mob')
                except Exception as ex:
                    logging_helper.log_debug("detect_lines error in game_manager: %s" % ex)
                    mob = None

                if mob:
                    # mob gefunden (x,y,w,h)
                    try:
                        x, y, w, h = mob
                        rotation.rotation(x, y)
                    except Exception as ex:
                        logging_helper.log_debug("rotation call failed: %s" % ex)
                    # nach Kampf evtl Loot verarbeiten
                    if loot:
                        self.loot_process()
                    return

                # Wenn kein Mob gefunden
                logging_helper.log_info("No target found — attempting movement")
                if loot:
                    self.loot_process()

                if move:
                    moved = False
                    try:
                        moved = pather.move_to_ref_location()
                    except Exception as ex:
                        logging_helper.log_error("pather.move_to_ref_location error: %s" % ex)

                    if not moved:
                        # navigiere zur Truhe, falls Bewegung nicht moeglich
                        self.navigate_to_treasure()
                return

            # Not in game — log prominently so user knows why bot is idle
            logging_helper.log_error(
                "⚠️ Bot idle — not in game! Is D4 in windowed fullscreen and visible?"
            )
            sleep(uniform(0.2, 0.5))
        except Exception as ex:
            logging_helper.log_error("💥 game_manager crashed: %s" % ex)

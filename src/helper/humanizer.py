"""
Humanization Engine for D4 Bot
Wraps input functions with human-like timing and behavior patterns.
Drop-in enhancement for DarkDBx framework.
"""
import time
import random
from functools import wraps
from typing import Optional

# ─── Timing Constants ──────────────────────────────────────

# Key press delays (seconds) - simulates human reaction time
KEY_PRESS_MIN = 0.08
KEY_PRESS_MAX = 0.25
KEY_HOLD_MIN = 0.05
KEY_HOLD_MAX = 0.15

# Combat rhythm - slightly faster
COMBAT_KEY_MIN = 0.04
COMBAT_KEY_MAX = 0.12

# Rest periods
REST_EVERY_MIN = 600   # 10 minutes
REST_EVERY_MAX = 900   # 15 minutes
REST_DURATION_MIN = 8  # seconds
REST_DURATION_MAX = 35

# Misclick rate (1-3%)
MISCLICK_RATE = 0.02

# Session limits
MAX_SESSION_MINUTES = 120  # 2 hours max continuous
COOLDOWN_MINUTES = 30      # then 30 min break


class Humanizer:
    """Human-like behavior overlay for bot inputs."""

    def __init__(self):
        self.session_start = time.time()
        self.last_rest = time.time()
        self.action_count = 0
        self.misclick_count = 0

    def human_delay(self, min_s: float = KEY_PRESS_MIN, max_s: float = KEY_PRESS_MAX):
        """Random delay between actions."""
        time.sleep(random.uniform(min_s, max_s))

    def should_rest(self) -> bool:
        """Check if it's time for a rest period."""
        elapsed = time.time() - self.last_rest
        if elapsed > random.randint(REST_EVERY_MIN, REST_EVERY_MAX):
            return True
        return False

    def do_rest(self):
        """Simulate a human taking a break."""
        duration = random.randint(REST_DURATION_MIN, REST_DURATION_MAX)
        print(f"[Humanizer] Resting for {duration}s...")
        time.sleep(duration)
        self.last_rest = time.time()

    def should_misclick(self) -> bool:
        """Randomly decide to misclick for human-like imperfection."""
        return random.random() < MISCLICK_RATE

    def humanized_press(self, key: str, combat: bool = False):
        """
        Press a key with human-like timing.
        combat=True uses faster timing (battle rhythm).
        """
        min_d, max_d = (COMBAT_KEY_MIN, COMBAT_KEY_MAX) if combat else (KEY_PRESS_MIN, KEY_PRESS_MAX)
        self.human_delay(min_d, max_d)

        # Occasionally hold key slightly longer
        if random.random() < 0.1:
            time.sleep(random.uniform(KEY_HOLD_MIN, KEY_HOLD_MAX))

        return key  # Return for chaining

    def session_check(self) -> bool:
        """Return True if session should continue, False if cooldown needed."""
        elapsed_minutes = (time.time() - self.session_start) / 60
        if elapsed_minutes > MAX_SESSION_MINUTES:
            print(f"[Humanizer] Max session ({MAX_SESSION_MINUTES}min) reached. Cooldown required.")
            return False
        return True


# ─── Decorator for monkey-patching ──────────────────────────

def humanize_press(original_press_fn):
    """Decorator to add human-like timing to key press."""
    h = Humanizer()

    @wraps(original_press_fn)
    def wrapper(key: str, *args, **kwargs):
        # Random pre-delay
        time.sleep(random.uniform(0.01, 0.08))
        # Check rest
        if h.should_rest():
            h.do_rest()
        # Check misclick
        if h.should_misclick():
            key_neighbors = {'1': '2', '2': '1', '3': '4', '4': '3',
                             'q': 'w', 'w': 'q', 'e': 'r', 'r': 'e'}
            if key in key_neighbors and random.random() < 0.5:
                original_press_fn(key_neighbors[key])
                time.sleep(random.uniform(0.05, 0.15))
                h.misclick_count += 1
        # Press the actual key
        result = original_press_fn(key, *args, **kwargs)
        h.action_count += 1
        return result

    return wrapper


# ─── Standalone usage ───────────────────────────────────────

if __name__ == "__main__":
    h = Humanizer()
    print(f"Humanizer initialized. Max session: {MAX_SESSION_MINUTES}min")
    print(f"Rest every: {REST_EVERY_MIN}-{REST_EVERY_MAX}s, duration: {REST_DURATION_MIN}-{REST_DURATION_MAX}s")
    print(f"Misclick rate: {MISCLICK_RATE*100}%")
    print(f"Ready for integration with DarkDBx bot engine.")

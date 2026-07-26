"""
Tunables. Every number here is a distribution parameter, never a constant,
because constants are the thing detectors find.
"""

from dataclasses import dataclass, field


# --- Session envelope (competition rule: 10s min, 60s max, per bot) ---------
SESSION_MIN_S = 12.0          # 2s safety margin over the 10s floor
SESSION_MAX_S = 54.0          # 6s margin under the 60s ceiling for teardown
SESSION_TARGET_MEAN_S = 31.0  # centre of the log-normal dwell draw


# --- Cursor dynamics --------------------------------------------------------
# Fitts's law: MT = a + b * log2(2D/W).  Human means from the HCI literature.
FITTS_A_S = 0.105
FITTS_B_S = 0.155
FITTS_NOISE_FRAC = 0.16       # per-movement gaussian noise on duration

CURVATURE_FRAC = (0.04, 0.14)  # perpendicular control-point offset / distance
TREMOR_PX = (0.4, 1.9)         # correlated hand-tremor amplitude
OVERSHOOT_PROB = 0.28          # chance of overshoot + corrective submovement
OVERSHOOT_FRAC = (0.04, 0.13)  # how far past the target we sail

# Real mice report at 125Hz; browsers coalesce to ~60Hz. Emit in that band.
EVENT_HZ = (58.0, 126.0)

CLICK_DWELL_MS = (42.0, 124.0)   # mousedown -> mouseup
CLICK_OFFCENTRE_FRAC = 0.22      # sigma as fraction of element half-extent


# --- Keystroke dynamics -----------------------------------------------------
KEY_DWELL_MS = (58.0, 122.0)     # keydown -> keyup for one key
FLIGHT_ALTERNATE_HAND_MS = 88.0  # faster: hands move in parallel
FLIGHT_SAME_HAND_MS = 132.0
FLIGHT_SAME_FINGER_MS = 187.0    # slowest: one finger must travel
FLIGHT_JITTER_FRAC = 0.27
THINK_PAUSE_PROB = 0.055         # mid-field hesitation
THINK_PAUSE_S = (0.30, 1.25)
TYPO_PROB = 0.028                # per character
TYPO_NOTICE_AFTER = (1, 3)       # chars typed before noticing


# --- Scroll dynamics --------------------------------------------------------
# A human flick = a burst of wheel events with decaying deltas, then a read.
WHEEL_BURST_EVENTS = (4, 11)
WHEEL_FIRST_DELTA = (88.0, 190.0)
WHEEL_DECAY = (0.78, 0.91)
WHEEL_EVENT_GAP_MS = (11.0, 27.0)
SCROLL_UP_PROB = 0.17            # humans scroll back to re-read


# --- Reading / idling -------------------------------------------------------
WORDS_PER_MINUTE = (190.0, 340.0)  # scanning, not careful reading
IDLE_DRIFT_PROB = 0.45             # aimless cursor drift while reading
HOVER_NO_CLICK_PROB = 0.5          # hover something you never click


# --- Fleet behaviour --------------------------------------------------------
# Poisson arrivals. Uniform spacing between bots is a cross-session signal.
FLEET_ARRIVAL_MEAN_S = 9.0
WARM_REFERRER_PROB = 0.72          # arriving with no Referer is a tell


@dataclass
class PersonaBias:
    """
    Per-bot multipliers. Without these, N bots share one behavioural
    distribution -- which is itself a detectable population-level signature.
    """
    speed: float = 1.0        # scales all durations
    precision: float = 1.0    # scales overshoot/tremor inversely
    patience: float = 1.0     # scales reading dwell
    scrolliness: float = 1.0  # scales scroll frequency
    device: str = "mouse"     # "mouse" | "trackpad"


@dataclass
class RunConfig:
    target: str = ""
    bots: int = 1
    concurrency: int = 1
    proxies: list[str] = field(default_factory=list)
    headless: bool = False    # headful under Xvfb is materially safer
    log_dir: str = "runs"

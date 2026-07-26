"""
Cursor trajectory synthesis.

Why not Bezier curves, which is what every tutorial suggests? Because a pure
Bezier path is *too smooth*. Real human reaching has four properties that a
Bezier lacks, and a behavioural scorer measures all four:

  1. A bell-shaped velocity profile (minimum-jerk), not constant speed.
  2. Physiological tremor -- low-frequency correlated noise, ~0.5-2px.
  3. Corrective submovements: humans overshoot, then make a fast small
     correction. Roughly 30% of reaches.
  4. Duration obeying Fitts's law -- time scales with log2(distance/width).
     A bot that takes the same 300ms to reach a near target and a far one is
     trivially separable, and this is the check I would write first.

We synthesise all four.
"""

from __future__ import annotations

import math
import random

import config as C


def _min_jerk(t: float) -> float:
    """Minimum-jerk position profile. Zero velocity and accel at both ends."""
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _fitts_duration(distance: float, target_w: float, rng: random.Random,
                    speed: float) -> float:
    w = max(target_w, 6.0)
    difficulty = math.log2((2.0 * max(distance, 1.0)) / w + 1.0)
    base = C.FITTS_A_S + C.FITTS_B_S * difficulty
    noisy = rng.gauss(base, base * C.FITTS_NOISE_FRAC)
    return max(0.05, noisy / max(speed, 0.2))


def _tremor_series(n: int, amp: float, rng: random.Random) -> list[float]:
    """
    Ornstein-Uhlenbeck-ish correlated noise. White noise would be wrong:
    real tremor is temporally correlated, so consecutive samples are similar.
    A detector computing the autocorrelation of cursor residuals can tell
    the difference between the two immediately.
    """
    theta, out, x = 0.22, [], 0.0
    for _ in range(n):
        x += -theta * x + rng.gauss(0.0, amp * 0.5)
        out.append(x)
    return out


def _leg(x0: float, y0: float, x1: float, y1: float, duration: float,
         rng: random.Random, tremor_amp: float) -> list[tuple[float, float, float]]:
    """One ballistic movement. Returns [(x, y, dt_seconds), ...]."""
    dx, dy = x1 - x0, y1 - y0
    distance = math.hypot(dx, dy)

    hz = rng.uniform(*C.EVENT_HZ)
    steps = max(2, int(duration * hz))

    # Perpendicular control point -> gentle natural arc.
    curve = rng.uniform(*C.CURVATURE_FRAC) * distance * rng.choice((-1.0, 1.0))
    if distance > 1e-6:
        px, py = -dy / distance, dx / distance
    else:
        px, py = 0.0, 0.0
    cx, cy = (x0 + x1) / 2 + px * curve, (y0 + y1) / 2 + py * curve

    tremor_x = _tremor_series(steps, tremor_amp, rng)
    tremor_y = _tremor_series(steps, tremor_amp, rng)

    pts: list[tuple[float, float, float]] = []
    for i in range(1, steps + 1):
        u = _min_jerk(i / steps)          # time -> arc-length remap
        omu = 1.0 - u
        bx = omu * omu * x0 + 2 * omu * u * cx + u * u * x1
        by = omu * omu * y0 + 2 * omu * u * cy + u * u * y1
        # Tremor fades to zero at the endpoint so we land precisely.
        fade = math.sin(math.pi * (i / steps)) ** 0.6
        dt = (duration / steps) * rng.uniform(0.82, 1.18)
        pts.append((bx + tremor_x[i - 1] * fade,
                    by + tremor_y[i - 1] * fade,
                    dt))
    return pts


def path_to(x0: float, y0: float, x1: float, y1: float, target_w: float,
            rng: random.Random, speed: float = 1.0,
            precision: float = 1.0) -> list[tuple[float, float, float]]:
    """
    Full reach from (x0,y0) to (x1,y1), possibly with overshoot + correction.
    """
    distance = math.hypot(x1 - x0, y1 - y0)
    tremor_amp = rng.uniform(*C.TREMOR_PX) / max(precision, 0.3)

    overshoots = (distance > 90.0
                  and rng.random() < C.OVERSHOOT_PROB / max(precision, 0.3))

    if not overshoots:
        dur = _fitts_duration(distance, target_w, rng, speed)
        return _leg(x0, y0, x1, y1, dur, rng, tremor_amp)

    # Primary ballistic phase sails past the target...
    frac = rng.uniform(*C.OVERSHOOT_FRAC)
    ox = x1 + (x1 - x0) * frac + rng.gauss(0, 3)
    oy = y1 + (y1 - y0) * frac + rng.gauss(0, 3)

    d1 = _fitts_duration(distance, target_w * 2.4, rng, speed) * 0.86
    pts = _leg(x0, y0, ox, oy, d1, rng, tremor_amp)

    # ...then a brief motor-planning gap before the correction.
    pts.append((ox, oy, rng.uniform(0.018, 0.055)))

    d2 = _fitts_duration(math.hypot(x1 - ox, y1 - oy), target_w, rng, speed) * 0.72
    pts += _leg(ox, oy, x1, y1, d2, rng, tremor_amp * 0.6)
    return pts


def click_point(box: dict, rng: random.Random) -> tuple[float, float]:
    """
    Humans do not click element centres. Click coordinates are gaussian about
    the centre. Every click landing on the exact integer centre of its bounding
    box is one of the loudest signals a bot can emit -- and it is free to fix.
    """
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    sx = max(1.0, box["width"] / 2 * C.CLICK_OFFCENTRE_FRAC)
    sy = max(1.0, box["height"] / 2 * C.CLICK_OFFCENTRE_FRAC)
    x = min(box["x"] + box["width"] - 2, max(box["x"] + 2, rng.gauss(cx, sx)))
    y = min(box["y"] + box["height"] - 2, max(box["y"] + 2, rng.gauss(cy, sy)))
    return x, y


def idle_drift(x: float, y: float, rng: random.Random,
               bounds: tuple[int, int]) -> list[tuple[float, float, float]]:
    """
    Small aimless movement while reading. Real cursors are never perfectly
    static for eight seconds; they twitch, drift, and get parked in odd places.
    """
    vw, vh = bounds
    out: list[tuple[float, float, float]] = []
    cx, cy = x, y
    for _ in range(rng.randint(1, 3)):
        nx = min(vw - 4, max(4, cx + rng.gauss(0, 42)))
        ny = min(vh - 4, max(4, cy + rng.gauss(0, 34)))
        out += _leg(cx, cy, nx, ny, rng.uniform(0.12, 0.42), rng,
                    rng.uniform(*C.TREMOR_PX))
        cx, cy = nx, ny
        out.append((cx, cy, rng.uniform(0.08, 0.5)))
    return out

"""
Scroll dynamics.

`window.scrollTo(0, 800)` produces exactly one scroll event and zero wheel
events. Real scrolling produces a *burst* of wheel events with decaying deltas
(a flick plus momentum), then a pause to read, then another burst. Mouse wheels
emit large quantised deltas; trackpads emit many small ones. Both differ from
programmatic scrolling in ways trivially visible from the event stream, and a
page that receives scroll events with no preceding wheel events has been
scrolled by code, not by a person.
"""

from __future__ import annotations

import random

import config as C


def wheel_burst(rng: random.Random, device: str = "mouse",
                direction: int = 1, intensity: float = 1.0) -> list[tuple[float, float]]:
    """One flick. Returns [(delta_y, gap_seconds), ...]."""
    out: list[tuple[float, float]] = []

    if device == "trackpad":
        # Trackpad: continuous surface, so the DELTA decays as the fingers
        # decelerate, with fine granularity and a long momentum tail.
        n = rng.randint(9, 24)
        delta = rng.uniform(22.0, 64.0) * intensity
        decay = rng.uniform(0.86, 0.96)
        for _ in range(n):
            out.append((delta * rng.uniform(0.86, 1.14) * direction,
                        rng.uniform(5.0, 14.0) / 1000.0))
            delta *= decay
            if abs(delta) < 6.0:
                break
        return out

    # Discrete wheel: each detent emits a FIXED unit (100px on Chromium,
    # 120 on some Windows setups). The delta therefore does not decay -- the
    # spin RATE does. Modelling decay in the delta instead of the gap is a
    # subtle but real error: it produces deltaY values no physical wheel can
    # emit, which is exactly the kind of thing worth getting right when the
    # opponent reads raw event streams for a living.
    notch = rng.choice((100.0, 120.0))
    n = rng.randint(*C.WHEEL_BURST_EVENTS)
    n = max(2, int(n * min(2.0, max(0.4, intensity))))
    gap = rng.uniform(*C.WHEEL_EVENT_GAP_MS) / 1000.0
    slow = rng.uniform(1.06, 1.22)      # inter-event gap lengthens as it slows

    for i in range(n):
        # Occasional double-detent when spinning fast.
        notches = 2 if (i < n * 0.4 and rng.random() < 0.22) else 1
        out.append((notch * notches * direction, gap * rng.uniform(0.85, 1.15)))
        gap *= slow
        if gap > 0.16:                  # wheel has effectively stopped
            break
    return out


def reading_plan(page_height: int, viewport_height: int, budget_s: float,
                 rng: random.Random, device: str = "mouse",
                 patience: float = 1.0,
                 scrolliness: float = 1.0) -> list[dict]:
    """
    Plan a read-through of the page inside a time budget.

    Produces a mix of scroll bursts and reading pauses, including occasional
    upward scrolls (humans re-read), and never scrolls past the bottom.
    """
    scrollable = max(0, page_height - viewport_height)
    plan: list[dict] = []
    spent = 0.0
    position = 0.0

    while spent < budget_s * 0.92:
        # Read where we are. Dwell scales with how much text a viewport holds.
        words = viewport_height * rng.uniform(0.16, 0.34)
        wpm = rng.uniform(*C.WORDS_PER_MINUTE)
        dwell = (words / wpm) * 60.0 * patience * rng.uniform(0.6, 1.5)
        # Clamp to BOTH a per-dwell ceiling and whatever budget actually remains,
        # or the plan overruns the competition's 60s hard ceiling.
        dwell = max(0.35, min(dwell, budget_s * 0.3, max(0.35, budget_s - spent)))

        plan.append({"type": "read", "seconds": dwell})
        spent += dwell
        if spent >= budget_s * 0.92:
            break

        if scrollable <= 0:
            plan.append({"type": "idle", "seconds": rng.uniform(0.4, 1.4)})
            spent += 0.8
            continue

        up = position > viewport_height and rng.random() < C.SCROLL_UP_PROB
        direction = -1 if up else 1
        burst = wheel_burst(rng, device, direction,
                            intensity=rng.uniform(0.7, 1.3) * scrolliness)
        travelled = sum(abs(d) for d, _ in burst)

        if not up and position + travelled > scrollable:
            if position >= scrollable - 4:
                plan.append({"type": "idle", "seconds": rng.uniform(0.5, 1.6)})
                spent += 1.0
                continue
            direction = -1
            burst = wheel_burst(rng, device, -1, intensity=rng.uniform(0.6, 1.0))
            travelled = sum(abs(d) for d, _ in burst)

        position = max(0.0, min(scrollable, position + travelled * direction))
        plan.append({"type": "wheel", "events": burst})
        spent += sum(g for _, g in burst)

    return plan

"""
Temporal distributions.

Human durations are log-normal, not uniform. `random.uniform(1, 3)` has a flat
histogram; no human behaviour does. Given enough samples across a bot fleet,
the shape of the distribution is itself the fingerprint -- so a protector who
aggregates across your bots can flag "uniformly distributed dwell times" even
if every individual session looks fine.
"""

from __future__ import annotations

import math
import random

import config as C


def lognormal_between(lo: float, hi: float, mean: float,
                      rng: random.Random) -> float:
    """Log-normal draw whose bulk sits near `mean`, truncated to [lo, hi]."""
    mu = math.log(max(mean, 1e-3))
    for _ in range(24):
        v = math.exp(rng.gauss(mu, 0.42))
        if lo <= v <= hi:
            return v
    return max(lo, min(hi, mean))


def session_budget(rng: random.Random, patience: float = 1.0) -> float:
    """Total on-site time for one bot, inside the competition's 10-60s window."""
    return lognormal_between(
        C.SESSION_MIN_S,
        C.SESSION_MAX_S,
        C.SESSION_TARGET_MEAN_S * patience,
        rng,
    )


def poisson_arrivals(n: int, mean_gap_s: float,
                     rng: random.Random) -> list[float]:
    """
    Exponential inter-arrival times -> a Poisson process.

    Launching bots every N seconds on the dot is a fleet-level signature that
    survives even perfect per-session realism. Real visitors arrive randomly.
    """
    t, out = 0.0, []
    for _ in range(n):
        t += rng.expovariate(1.0 / max(mean_gap_s, 0.2))
        out.append(t)
    return out


def reaction_delay(rng: random.Random) -> float:
    """Simple-reaction latency before acting on something newly visible."""
    return lognormal_between(0.14, 1.5, 0.34, rng)

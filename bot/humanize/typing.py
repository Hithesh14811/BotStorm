"""
Keystroke dynamics.

`page.type(text, delay=100)` is a giveaway: constant inter-key delay does not
occur in human typing. Even `delay=random(80,150)` is wrong, because real
inter-key timing is *structured*, not uniform noise -- it depends on which
fingers and hands type the two characters:

  - alternating hands  -> fastest (the hands move in parallel)
  - same hand, differing fingers -> slower
  - same finger twice   -> slowest (one finger must physically travel)

Keystroke-dynamics biometrics have been a solved research area since the 1980s
and are cheap to implement, so assume the protector implements them. We model
the digraph structure, plus dwell time, hesitation, and typo-and-correct.
"""

from __future__ import annotations

import random

import config as C


# QWERTY -> (hand, finger-id). Finger ids are unique per hand.
_LAYOUT = {
    "1": ("L", 1), "2": ("L", 2), "3": ("L", 3), "4": ("L", 4), "5": ("L", 4),
    "6": ("R", 4), "7": ("R", 4), "8": ("R", 3), "9": ("R", 2), "0": ("R", 1),
    "q": ("L", 1), "w": ("L", 2), "e": ("L", 3), "r": ("L", 4), "t": ("L", 4),
    "y": ("R", 4), "u": ("R", 4), "i": ("R", 3), "o": ("R", 2), "p": ("R", 1),
    "a": ("L", 1), "s": ("L", 2), "d": ("L", 3), "f": ("L", 4), "g": ("L", 4),
    "h": ("R", 4), "j": ("R", 4), "k": ("R", 3), "l": ("R", 2), ";": ("R", 1),
    "z": ("L", 1), "x": ("L", 2), "c": ("L", 3), "v": ("L", 4), "b": ("L", 4),
    "n": ("R", 4), "m": ("R", 4), ",": ("R", 3), ".": ("R", 2), "/": ("R", 1),
    "-": ("R", 1), "_": ("R", 1), "@": ("L", 2), "'": ("R", 1), " ": ("R", 0),
}

# Physically adjacent keys, for realistic typos. A typo of 'a' -> 'z' is
# believable; 'a' -> 'p' is not, and a mistyped-then-corrected character that
# is nowhere near the intended key looks synthetic.
_ADJACENT = {
    "a": "qwsz", "b": "vghn", "c": "xdfv", "d": "serfcx", "e": "wsdr",
    "f": "drtgvc", "g": "ftyhbv", "h": "gyujnb", "i": "ujko", "j": "huikmn",
    "k": "jiolm", "l": "kop", "m": "njk", "n": "bhjm", "o": "iklp",
    "p": "ol", "q": "wa", "r": "edft", "s": "awedxz", "t": "rfgy",
    "u": "yhji", "v": "cfgb", "w": "qase", "x": "zsdc", "y": "tghu",
    "z": "asx", "1": "2q", "2": "13w", "3": "24e", "4": "35r", "5": "46t",
    "6": "57y", "7": "68u", "8": "79i", "9": "80o", "0": "9p",
}


def _flight_ms(prev: str, cur: str, rng: random.Random) -> float:
    p = _LAYOUT.get(prev.lower())
    c = _LAYOUT.get(cur.lower())
    if not p or not c:
        base = C.FLIGHT_SAME_HAND_MS
    elif p[0] != c[0]:
        base = C.FLIGHT_ALTERNATE_HAND_MS
    elif p[1] == c[1]:
        base = C.FLIGHT_SAME_FINGER_MS
    else:
        base = C.FLIGHT_SAME_HAND_MS

    # Shift for capitals and symbols costs real time.
    if cur.isupper() or cur in '!@#$%^&*()_+{}|:"<>?':
        base *= 1.32

    return max(18.0, rng.gauss(base, base * C.FLIGHT_JITTER_FRAC))


def keystroke_plan(text: str, rng: random.Random,
                   speed: float = 1.0) -> list[dict]:
    """
    Compile text into a timed keystroke programme.

    Each entry: {"key", "dwell_s", "pre_delay_s"}. A "key" of "\b" means
    Backspace. Emits deliberate typos followed by realistic corrections.
    """
    plan: list[dict] = []
    prev = " "
    i = 0
    fumbled: set[int] = set()   # never fumble the same index twice

    while i < len(text):
        ch = text[i]

        # Occasional mid-field hesitation, as when a human thinks.
        pre = _flight_ms(prev, ch, rng) / 1000.0 / max(speed, 0.25)
        if rng.random() < C.THINK_PAUSE_PROB:
            pre += rng.uniform(*C.THINK_PAUSE_S)

        make_typo = (ch.isalnum()
                     and ch.lower() in _ADJACENT
                     and i not in fumbled
                     and rng.random() < C.TYPO_PROB)

        if make_typo:
            fumbled.add(i)
            wrong = rng.choice(_ADJACENT[ch.lower()])
            if ch.isupper():
                wrong = wrong.upper()
            plan.append({
                "key": wrong,
                "dwell_s": rng.uniform(*C.KEY_DWELL_MS) / 1000.0,
                "pre_delay_s": pre,
            })

            # Type a few more characters before noticing the error.
            noticed_after = rng.randint(*C.TYPO_NOTICE_AFTER)
            extra = text[i + 1:i + 1 + noticed_after]
            p = wrong
            for e in extra:
                plan.append({
                    "key": e,
                    "dwell_s": rng.uniform(*C.KEY_DWELL_MS) / 1000.0,
                    "pre_delay_s": _flight_ms(p, e, rng) / 1000.0 / max(speed, 0.25),
                })
                p = e

            # Notice, pause, then backspace over the bad run.
            plan.append({
                "key": "\b",
                "dwell_s": rng.uniform(40, 90) / 1000.0,
                "pre_delay_s": rng.uniform(0.16, 0.52),
            })
            for _ in range(len(extra)):
                plan.append({
                    "key": "\b",
                    "dwell_s": rng.uniform(35, 75) / 1000.0,
                    "pre_delay_s": rng.uniform(0.045, 0.12),
                })
            # Retype correctly, starting from the character we fumbled.
            prev = "\b"
            continue

        plan.append({
            "key": ch,
            "dwell_s": rng.uniform(*C.KEY_DWELL_MS) / 1000.0,
            "pre_delay_s": pre,
        })
        prev = ch
        i += 1

    return plan

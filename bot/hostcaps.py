"""
Host capability probing.

Why this module exists
---------------------
`public/probe.js` -- and every serious commercial detector -- does NOT ask the
browser "which fonts do you have?". It *measures* them: render a string in the
candidate family, render it in a generic fallback, and compare `offsetWidth`.
A family only counts as present if it actually changes the rasterised width.

That distinction is fatal for naive spoofing. Camoufox's `fonts` launch option
controls the font list the browser *reports and permits*, but it cannot
conjure glyph outlines that are not on the machine. So the set a detector can
actually measure is bounded by what fontconfig has installed:

    measurable  ⊆  installed ∩ claimed

If a persona claims to be macOS on a bare Linux container, the claimed set is
~58 families while the measurable set is ~3. `lib/score.ts` scores that as
`fonts` sparse (weight 25), and worse, "claims Helvetica Neue but cannot
render it" is a zero-false-positive contradiction -- no real Mac fails to
render Helvetica Neue.

Apple's system fonts are also not redistributable, so they will never be
present on a Linux node. Therefore macOS personas are **not viable** on Linux
and this module drops them automatically rather than shipping a contradiction.

The rule enforced here: never claim an OS whose signature fonts the host
cannot actually rasterise.
"""

from __future__ import annotations

import functools
import os
import shutil
import subprocess
from dataclasses import dataclass, field


# The families a detector actually probes for, per OS. These are the
# high-signal ones: present on essentially every real install of that OS, and
# absent (or licence-locked) elsewhere. Coverage is measured against these,
# not against the full decorative tail, because missing "Zapfino" proves
# nothing while missing "Helvetica Neue" proves everything.
OS_SIGNATURE_FONTS = {
    "windows": [
        "Segoe UI", "Calibri", "Cambria", "Consolas", "Tahoma",
        "Times New Roman", "Arial", "Verdana", "Georgia", "Trebuchet MS",
        "Courier New", "Impact", "Comic Sans MS", "Palatino Linotype",
    ],
    "macos": [
        "Helvetica", "Helvetica Neue", "Menlo", "Monaco", "Lucida Grande",
        "Geneva", "Optima", "Futura", "Baskerville", "Palatino",
        "Hoefler Text", "Gill Sans", "Courier", "Times",
    ],
    "linux": [
        "DejaVu Sans", "DejaVu Serif", "DejaVu Sans Mono",
        "Liberation Sans", "Liberation Serif", "Liberation Mono",
        "Noto Sans", "Noto Serif",
    ],
}

# Fraction of the signature set that must genuinely rasterise before we allow
# a persona to claim that OS. Real installs vary a little (a user can uninstall
# Comic Sans), so this is not 1.0 -- but it is high enough that a container
# with only DejaVu can never masquerade as Windows.
DEFAULT_MIN_COVERAGE = 0.85


@dataclass
class HostCaps:
    """What this machine can actually prove about itself."""

    installed: set[str]                      # normalised family names
    coverage: dict[str, float]               # os -> fraction of signature set
    viable_os: list[str]                     # OS values safe to impersonate
    missing: dict[str, list[str]] = field(default_factory=dict)
    source: str = "fontconfig"

    def fonts_for(self, os_name: str, candidates: list[str]) -> list[str]:
        """
        Narrow a persona's claimed font list to families that will really
        rasterise. Guarantees claimed == measurable, which is what removes the
        contradiction the scorer looks for.
        """
        return [f for f in candidates if _norm(f) in self.installed]

    def report(self) -> str:
        lines = [f"host font source: {self.source}",
                 f"installed families: {len(self.installed)}"]
        for os_name in ("windows", "macos", "linux"):
            cov = self.coverage.get(os_name, 0.0)
            mark = "VIABLE" if os_name in self.viable_os else "unusable"
            lines.append(f"  {os_name:<8} coverage={cov:5.1%}  {mark}")
            miss = self.missing.get(os_name) or []
            if miss and os_name not in self.viable_os:
                lines.append(f"      missing: {', '.join(miss[:6])}"
                             + (" ..." if len(miss) > 6 else ""))
        return "\n".join(lines)


def _norm(name: str) -> str:
    """Case/space-insensitive family key. fontconfig is inconsistent here."""
    return " ".join(name.strip().lower().split())


def _families_from_fc_list() -> set[str]:
    """
    Ask fontconfig for installed families. This is the same database Firefox
    itself uses on Linux, so it is the authoritative answer to "will this
    rasterise".
    """
    fc = shutil.which("fc-list")
    if not fc:
        return set()
    try:
        out = subprocess.run(
            [fc, ":", "family"],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout
    except Exception:
        return set()

    families: set[str] = set()
    for line in out.splitlines():
        # A line may carry several comma-separated aliases:
        #   "Noto Sans,Noto Sans Regular"
        for alias in line.split(","):
            alias = alias.strip()
            if alias:
                families.add(_norm(alias))
    return families


def _families_from_filenames() -> set[str]:
    """
    Fallback when fontconfig is absent. Filenames map to family names only
    roughly, so this is deliberately conservative -- it exists to keep local
    development working, not to certify a production node.
    """
    roots = [
        "/usr/share/fonts", "/usr/local/share/fonts",
        os.path.expanduser("~/.fonts"),
        os.path.expanduser("~/.local/share/fonts"),
        "/Library/Fonts", "/System/Library/Fonts",
        "C:\\Windows\\Fonts",
    ]
    families: set[str] = set()
    for root in roots:
        if not os.path.isdir(root):
            continue
        for dirpath, _dirnames, filenames in os.walk(root):
            for fn in filenames:
                stem, ext = os.path.splitext(fn)
                if ext.lower() not in (".ttf", ".otf", ".ttc", ".pfb"):
                    continue
                # "LiberationSans-Regular" -> "liberation sans"
                stem = stem.split("-")[0]
                spaced = "".join(
                    (" " + c if c.isupper() and i else c)
                    for i, c in enumerate(stem)
                )
                families.add(_norm(spaced))
                families.add(_norm(stem))
    return families


@functools.lru_cache(maxsize=1)
def host_capabilities(
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> HostCaps:
    """
    Probe once per process and cache. Called at worker startup so a
    misconfigured node fails immediately and loudly, instead of quietly
    emitting detectable traffic for 24 hours.
    """
    installed = _families_from_fc_list()
    source = "fontconfig"
    if not installed:
        installed = _families_from_filenames()
        source = "filename-scan (fontconfig missing)"

    coverage: dict[str, float] = {}
    missing: dict[str, list[str]] = {}
    viable: list[str] = []

    for os_name, sig in OS_SIGNATURE_FONTS.items():
        absent = [f for f in sig if _norm(f) not in installed]
        present = len(sig) - len(absent)
        cov = present / len(sig) if sig else 0.0
        coverage[os_name] = cov
        missing[os_name] = absent
        if cov >= min_coverage:
            viable.append(os_name)

    return HostCaps(
        installed=installed,
        coverage=coverage,
        viable_os=viable,
        missing=missing,
        source=source,
    )


class NoViablePersonaError(RuntimeError):
    """Raised when the host cannot honestly impersonate any desktop OS."""


def assert_viable(caps: HostCaps | None = None) -> HostCaps:
    """
    Guard for worker startup. Refusing to launch is strictly better than
    launching something a detector will flag: a bot that never ran costs you
    nothing, a bot that ran and got caught costs you the round.
    """
    caps = caps or host_capabilities()
    if not caps.viable_os:
        raise NoViablePersonaError(
            "No OS can be safely impersonated on this host.\n"
            + caps.report()
            + "\n\nFix: install real font sets into the container image, e.g.\n"
              "  apt-get install -y fontconfig fonts-liberation "
              "fonts-dejavu fonts-noto-core\n"
              "  # Windows personas additionally need:\n"
              "  apt-get install -y ttf-mscorefonts-installer\n"
              "Apple system fonts are not redistributable, so macOS personas "
              "are not achievable on Linux nodes."
        )
    return caps


if __name__ == "__main__":  # pragma: no cover - operator convenience
    caps = host_capabilities()
    print(caps.report())
    print()
    if caps.viable_os:
        print("OK: can impersonate ->", ", ".join(caps.viable_os))
    else:
        print("FAIL: no viable persona OS on this host")

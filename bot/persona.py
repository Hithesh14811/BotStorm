"""
Persona generation.

The failure mode that kills most stealth bots is not a missing spoof -- it is
an INCONSISTENT one. A Windows user-agent with macOS fonts, a São Paulo exit
IP with Asia/Kolkata timezone, or a 1366x768 screen reporting 8 GB of VRAM are
all instantly fatal, and they are exactly what a detector who built AdSense
heuristics will look for first, because they are cheap to check and never
produce false positives on real traffic.

So: every attribute of a persona is derived from one coherent device identity,
and the geo attributes are derived from the *actual* proxy exit IP.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

import httpx

from config import PersonaBias


# Real device profiles. Screen metrics, DPR and fonts are internally coherent.
# Market-share weighted -- a rare resolution is itself an anomaly.
DEVICE_PROFILES = [
    {
        "name": "win11-1080p",
        "weight": 30,
        "os": "windows",
        "screen": (1920, 1080),
        "avail": (1920, 1032),
        "dpr": 1.0,
        "viewport": (1536, 776),
        "cores": 8,
        "memory": 8,
        "touch": 0,
    },
    {
        "name": "win11-1440p",
        "weight": 11,
        "os": "windows",
        "screen": (2560, 1440),
        "avail": (2560, 1392),
        "dpr": 1.0,
        "viewport": (2048, 1080),
        "cores": 12,
        "memory": 16,
        "touch": 0,
    },
    {
        "name": "win10-laptop-768",
        "weight": 17,
        "os": "windows",
        "screen": (1366, 768),
        "avail": (1366, 728),
        "dpr": 1.0,
        "viewport": (1366, 641),
        "cores": 4,
        "memory": 8,
        "touch": 0,
    },
    {
        "name": "win11-laptop-scaled",
        "weight": 9,
        "os": "windows",
        "screen": (1536, 864),
        "avail": (1536, 824),
        "dpr": 1.25,
        "viewport": (1536, 738),
        "cores": 8,
        "memory": 16,
        "touch": 0,
    },
    {
        "name": "macbook-air-m2",
        "weight": 13,
        "os": "macos",
        "screen": (1470, 956),
        "avail": (1470, 931),
        "dpr": 2.0,
        "viewport": (1470, 831),
        "cores": 8,
        "memory": 8,
        "touch": 0,
    },
    {
        "name": "macbook-pro-14",
        "weight": 8,
        "os": "macos",
        "screen": (1512, 982),
        "avail": (1512, 957),
        "dpr": 2.0,
        "viewport": (1512, 857),
        "cores": 10,
        "memory": 16,
        "touch": 0,
    },
    {
        "name": "linux-1080p",
        "weight": 3,
        "os": "linux",
        "screen": (1920, 1080),
        "avail": (1920, 1053),
        "dpr": 1.0,
        "viewport": (1920, 979),
        "cores": 8,
        "memory": 16,
        "touch": 0,
    },
]


# WebGL vendor/renderer pairs must be plausible FOR THE OS.
# A macOS UA reporting "ANGLE (NVIDIA GeForce...)" is a contradiction.
WEBGL_BY_OS = {
    "windows": [
        ("Google Inc. (NVIDIA)",
         "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) UHD Graphics 620 Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (Intel)",
         "ANGLE (Intel, Intel(R) Iris(R) Xe Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
        ("Google Inc. (AMD)",
         "ANGLE (AMD, AMD Radeon(TM) Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)"),
    ],
    "macos": [
        ("Apple", "Apple M2"),
        ("Apple", "Apple M3"),
        ("Apple", "Apple M1"),
    ],
    "linux": [
        ("Mesa", "Mesa Intel(R) UHD Graphics (CML GT2)"),
        ("Mesa/X.org", "llvmpipe (LLVM 15.0.7, 256 bits)"),
    ],
}


FONTS_BY_OS = {
    "windows": [
        "Arial", "Arial Black", "Bahnschrift", "Calibri", "Cambria",
        "Candara", "Comic Sans MS", "Consolas", "Constantia", "Corbel",
        "Courier New", "Ebrima", "Franklin Gothic Medium", "Gabriola",
        "Gadugi", "Georgia", "Impact", "Ink Free", "Javanese Text",
        "Leelawadee UI", "Lucida Console", "Lucida Sans Unicode",
        "Malgun Gothic", "Marlett", "Microsoft Himalaya", "Microsoft JhengHei",
        "Microsoft New Tai Lue", "Microsoft PhagsPa", "Microsoft Sans Serif",
        "Microsoft Tai Le", "Microsoft YaHei", "MingLiU-ExtB", "Mongolian Baiti",
        "MS Gothic", "MV Boli", "Myanmar Text", "Nirmala UI", "Palatino Linotype",
        "Segoe MDL2 Assets", "Segoe Print", "Segoe Script", "Segoe UI",
        "Segoe UI Emoji", "Segoe UI Historic", "Segoe UI Symbol", "SimSun",
        "Sitka", "Sylfaen", "Symbol", "Tahoma", "Times New Roman",
        "Trebuchet MS", "Verdana", "Webdings", "Wingdings", "Yu Gothic",
    ],
    "macos": [
        "American Typewriter", "Andale Mono", "Arial", "Arial Black",
        "Arial Narrow", "Arial Rounded MT Bold", "Arial Unicode MS",
        "Avenir", "Avenir Next", "Avenir Next Condensed", "Baskerville",
        "Big Caslon", "Bodoni 72", "Bradley Hand", "Brush Script MT",
        "Chalkboard", "Chalkduster", "Charter", "Cochin", "Comic Sans MS",
        "Copperplate", "Courier", "Courier New", "Didot", "DIN Alternate",
        "DIN Condensed", "Futura", "Geneva", "Georgia", "Gill Sans",
        "Helvetica", "Helvetica Neue", "Herculanum", "Hoefler Text",
        "Impact", "Lucida Grande", "Luminari", "Marker Felt", "Menlo",
        "Microsoft Sans Serif", "Monaco", "Noteworthy", "Optima",
        "Palatino", "Papyrus", "Phosphate", "Rockwell", "San Francisco",
        "Savoye LET", "SignPainter", "Skia", "Snell Roundhand", "Tahoma",
        "Times", "Times New Roman", "Trattatello", "Trebuchet MS",
        "Verdana", "Zapfino",
    ],
    "linux": [
        "Cantarell", "DejaVu Sans", "DejaVu Sans Mono", "DejaVu Serif",
        "Liberation Mono", "Liberation Sans", "Liberation Serif",
        "Noto Color Emoji", "Noto Mono", "Noto Sans", "Noto Serif",
        "Ubuntu", "Ubuntu Condensed", "Ubuntu Mono",
    ],
}


@dataclass
class Persona:
    seed: str
    profile: dict
    webgl_vendor: str
    webgl_renderer: str
    fonts: list[str]
    locale: str
    timezone: str
    country: str | None
    latitude: float | None
    longitude: float | None
    bias: PersonaBias

    @property
    def os(self) -> str:
        return self.profile["os"]

    def rng(self, salt: str = "") -> random.Random:
        """
        Deterministic per-persona RNG. Canvas/audio noise MUST be stable within
        a session: if a detector reads the same canvas twice and gets two
        different hashes, that is not a human, and naive noise injection is the
        single most common way anti-detect browsers give themselves away.
        """
        h = hashlib.sha256(f"{self.seed}:{salt}".encode()).digest()
        return random.Random(int.from_bytes(h[:8], "big"))


def _weighted_choice(rng: random.Random, items: list[dict]) -> dict:
    total = sum(i["weight"] for i in items)
    r = rng.uniform(0, total)
    acc = 0.0
    for item in items:
        acc += item["weight"]
        if r <= acc:
            return item
    return items[-1]


# Country -> (timezone, locale). Extend as the organizers' proxy pool dictates.
GEO_DEFAULTS = {
    "IN": ("Asia/Kolkata", "en-IN"),
    "US": ("America/New_York", "en-US"),
    "GB": ("Europe/London", "en-GB"),
    "DE": ("Europe/Berlin", "de-DE"),
    "FR": ("Europe/Paris", "fr-FR"),
    "BR": ("America/Sao_Paulo", "pt-BR"),
    "SG": ("Asia/Singapore", "en-SG"),
    "AU": ("Australia/Sydney", "en-AU"),
    "CA": ("America/Toronto", "en-CA"),
    "NL": ("Europe/Amsterdam", "nl-NL"),
    "JP": ("Asia/Tokyo", "ja-JP"),
    "AE": ("Asia/Dubai", "en-AE"),
}


def probe_proxy_geo(proxy: str | None, timeout: float = 12.0) -> dict:
    """
    Resolve the ACTUAL exit-IP geography by querying through the proxy.

    This is not optional polish. Rotating residential proxies give you an exit
    node whose country you do not control, and a timezone that disagrees with
    the IP is the highest-confidence, zero-false-positive bot signal there is.
    Always derive geo from the exit, never from a guess.
    """
    endpoints = [
        "https://ipinfo.io/json",
        "https://ipapi.co/json/",
    ]
    for url in endpoints:
        try:
            with httpx.Client(proxy=proxy, timeout=timeout) as client:
                data = client.get(url).json()
            country = data.get("country") or data.get("country_code")
            tz = data.get("timezone")
            loc = data.get("loc")
            lat = lon = None
            if loc and "," in str(loc):
                lat, lon = (float(x) for x in str(loc).split(",")[:2])
            else:
                lat = data.get("latitude")
                lon = data.get("longitude")
            if country:
                return {
                    "country": country,
                    "timezone": tz,
                    "latitude": lat,
                    "longitude": lon,
                    "ip": data.get("ip"),
                }
        except Exception:
            continue
    return {}


def build_persona(seed: str, proxy: str | None = None) -> Persona:
    rng = random.Random(hashlib.sha256(seed.encode()).hexdigest())

    profile = _weighted_choice(rng, DEVICE_PROFILES)
    os_name = profile["os"]
    vendor, renderer = rng.choice(WEBGL_BY_OS[os_name])

    # Font list: take the OS base set and drop a few, as real installs vary.
    base_fonts = FONTS_BY_OS[os_name][:]
    drop = rng.sample(range(len(base_fonts)), k=rng.randint(0, 4))
    fonts = [f for i, f in enumerate(base_fonts) if i not in drop]

    geo = probe_proxy_geo(proxy) if proxy else {}
    country = geo.get("country")
    tz_default, locale_default = GEO_DEFAULTS.get(
        country or "", ("Asia/Kolkata", "en-IN")
    )
    timezone = geo.get("timezone") or tz_default
    locale = locale_default

    bias = PersonaBias(
        speed=rng.uniform(0.74, 1.34),
        precision=rng.uniform(0.68, 1.32),
        patience=rng.uniform(0.66, 1.45),
        scrolliness=rng.uniform(0.6, 1.5),
        device="trackpad" if (os_name == "macos" and rng.random() < 0.8)
        else ("trackpad" if rng.random() < 0.28 else "mouse"),
    )

    return Persona(
        seed=seed,
        profile=profile,
        webgl_vendor=vendor,
        webgl_renderer=renderer,
        fonts=fonts,
        locale=locale,
        timezone=timezone,
        country=country,
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
        bias=bias,
    )


def camoufox_config(p: Persona) -> dict:
    """
    Map a persona onto Camoufox's fingerprint override surface. Camoufox applies
    these inside the Firefox C++ source, so there is no JS-visible patch, no
    toString leak, and no property-descriptor anomaly to find.
    """
    sw, sh = p.profile["screen"]
    aw, ah = p.profile["avail"]
    vw, vh = p.profile["viewport"]
    return {
        "window.screen.width": sw,
        "window.screen.height": sh,
        "window.screen.availWidth": aw,
        "window.screen.availHeight": ah,
        "window.screen.colorDepth": 24,
        "window.screen.pixelDepth": 24,
        "window.devicePixelRatio": p.profile["dpr"],
        "window.innerWidth": vw,
        "window.innerHeight": vh,
        "window.outerWidth": sw,
        "window.outerHeight": ah,
        "navigator.hardwareConcurrency": p.profile["cores"],
        "navigator.maxTouchPoints": p.profile["touch"],
        "webGl:vendor": p.webgl_vendor,
        "webGl:renderer": p.webgl_renderer,
        "fonts": p.fonts,
    }

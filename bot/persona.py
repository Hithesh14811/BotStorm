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
import re
from dataclasses import dataclass

import httpx

from config import PersonaBias
from hostcaps import OS_SIGNATURE_FONTS, HostCaps, assert_viable


# Height of Firefox's own chrome (tab strip + nav toolbar, no bookmarks bar),
# i.e. outerHeight - innerHeight. Horizontally Firefox has no window border on
# any modern desktop OS, so outerWidth == innerWidth exactly.
#
# This delta is the geometry signal that matters. A window claiming
# outerWidth == screen.width while innerWidth is 1536 implies 384px of
# horizontal browser chrome, which cannot exist -- and it survives every
# "inner <= outer <= avail <= screen" sanity check, so a detector that looks
# at the *delta* rather than the ordering catches it immediately.
FIREFOX_CHROME_PX = {"windows": 82, "macos": 74, "linux": 78}

# OS furniture that reduces the available area. If availHeight == height AND
# availWidth == width, CreepJS's noTaskbar flag fires -- a headless tell.
TASKBAR_PX = {"windows": 40, "macos": 25, "linux": 27}


# Real device profiles. Screen metrics and fonts are internally coherent.
# Market-share weighted -- a rare resolution is itself an anomaly.
#
# "viewport" is the INNER (layout) size. Outer size is derived as
# (innerWidth, innerHeight + chrome) by outer_size(), never stored, so the two
# can never drift apart.
#
# devicePixelRatio is deliberately absent: Camoufox cannot spoof it coherently
# (browserforge.yml: "devicePixelRatio is not recommended. Any value other
# than 1.0 is suspicious"), and under Xvfb the real ratio is 1.0. A persona
# claiming 2.0 contradicts matchMedia('(resolution: 2dppx)') and the real
# rendering scale. So every profile is a genuine 1.0-DPR display, which rules
# out Retina MacBook panels -- the macOS personas below are on external
# monitors instead.
DEVICE_PROFILES = [
    {
        "name": "win11-1080p-max",
        "weight": 30,
        "os": "windows",
        "screen": (1920, 1080),
        "avail": (1920, 1040),
        "avail_origin": (0, 0),
        "viewport": (1920, 958),
        "maximized": True,
        "cores": 8,
        "touch": 0,
    },
    {
        "name": "win11-1080p-windowed",
        "weight": 10,
        "os": "windows",
        "screen": (1920, 1080),
        "avail": (1920, 1040),
        "avail_origin": (0, 0),
        "viewport": (1536, 776),
        "maximized": False,
        "cores": 8,
        "touch": 0,
    },
    {
        "name": "win11-1440p-max",
        "weight": 9,
        "os": "windows",
        "screen": (2560, 1440),
        "avail": (2560, 1400),
        "avail_origin": (0, 0),
        "viewport": (2560, 1318),
        "maximized": True,
        "cores": 12,
        "touch": 0,
    },
    {
        "name": "win10-laptop-768-max",
        "weight": 17,
        "os": "windows",
        "screen": (1366, 768),
        "avail": (1366, 728),
        "avail_origin": (0, 0),
        "viewport": (1366, 646),
        "maximized": True,
        "cores": 4,
        "touch": 0,
    },
    {
        "name": "win11-1536x864-max",
        "weight": 12,
        "os": "windows",
        "screen": (1536, 864),
        "avail": (1536, 824),
        "avail_origin": (0, 0),
        "viewport": (1536, 742),
        "maximized": True,
        "cores": 8,
        "touch": 0,
    },
    {
        "name": "mac-1080p-external-max",
        "weight": 9,
        "os": "macos",
        "screen": (1920, 1080),
        "avail": (1920, 1055),
        "avail_origin": (0, 25),   # menu bar
        "viewport": (1920, 981),
        "maximized": True,
        "cores": 8,
        "touch": 0,
    },
    {
        "name": "mac-1680x1050-max",
        "weight": 5,
        "os": "macos",
        "screen": (1680, 1050),
        "avail": (1680, 1025),
        "avail_origin": (0, 25),
        "viewport": (1680, 951),
        "maximized": True,
        "cores": 8,
        "touch": 0,
    },
    {
        "name": "linux-1080p-max",
        "weight": 3,
        "os": "linux",
        "screen": (1920, 1080),
        "avail": (1920, 1053),
        "avail_origin": (0, 27),   # GNOME top bar
        "viewport": (1920, 975),
        "maximized": True,
        "cores": 8,
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
    # Linux strings must name a real, consumer-grade GPU.
    #
    # The previous "llvmpipe (LLVM 15.0.7, 256 bits)" entry was an
    # own-goal: lib/score.ts matches
    #     /SwiftShader|llvmpipe|Mesa OffScreen|Software/i
    # at weight 40, severity FATAL. Any persona that drew it auto-failed
    # before doing anything else.
    #
    # We also avoid the substring "LLVM" altogether. A genuine radeonsi
    # renderer really does report "... LLVM 15.0.7, DRM 3.49 ...", but a
    # detector grepping the looser /llvm/i would still flag it, and we gain
    # nothing by betting on the opponent's regex being precise.
    #
    # NB: never expose a datacenter accelerator here either. On a GPU node
    # Firefox would report an NVIDIA H200 -- no human blog reader owns one,
    # which is why the browser fleet must run on CPU nodes with the GPU
    # hidden from the browser process.
    "linux": [
        ("Mesa", "Mesa Intel(R) UHD Graphics (CML GT2)"),
        ("Mesa", "Mesa Intel(R) Xe Graphics (TGL GT2)"),
        ("Mesa", "Mesa Intel(R) HD Graphics 620 (KBL GT2)"),
        ("AMD", "AMD Radeon RX 6600 (navi23, DRM 3.49)"),
    ],
}


# Anything matching this must never reach a fingerprint. Kept in sync with the
# scorer's software-renderer test, plus "llvm" as a defensive superset.
SOFTWARE_RENDERER_PAT = re.compile(
    r"swiftshader|llvmpipe|llvm|mesa offscreen|software|virgl|vgem",
    re.I,
)

# Datacenter parts a consumer machine cannot have. Guards against a real-GPU
# leak if someone runs the fleet on an accelerator node by mistake.
DATACENTER_GPU_PAT = re.compile(
    r"\b(h100|h200|a100|l4|l40|t4|v100|tesla|quadro|rtx\s*6000\s*ada|grid)\b",
    re.I,
)


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
    locale: str            # primary tag, e.g. "en-IN" (drives the Intl API)
    locales: list[str]     # full chain -> navigator.languages / Accept-Language
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


# Country -> (timezone, [locale chain]).
#
# The chain is a LIST, not a single tag, and that matters. Camoufox only emits
# `locale:all` (which drives navigator.languages and Accept-Language) when it
# is given two or more locales -- handle_locales() returns early on a
# single-element list. Passing just "en-IN" therefore leaves navigator.languages
# at whatever the randomly generated fingerprint happened to contain, so
# navigator.language and navigator.languages[0] can disagree. That is a
# zero-false-positive bot signal, and it is free to avoid.
#
# Real users almost always have a fallback chain: the bare region tag followed
# by the base language, plus English for non-anglophone locales.
GEO_DEFAULTS = {
    "IN": ("Asia/Kolkata", ["en-IN", "en", "hi"]),
    "US": ("America/New_York", ["en-US", "en"]),
    "GB": ("Europe/London", ["en-GB", "en"]),
    "DE": ("Europe/Berlin", ["de-DE", "de", "en-US", "en"]),
    "FR": ("Europe/Paris", ["fr-FR", "fr", "en-US", "en"]),
    "BR": ("America/Sao_Paulo", ["pt-BR", "pt", "en-US", "en"]),
    "SG": ("Asia/Singapore", ["en-SG", "en", "zh-CN", "zh"]),
    "AU": ("Australia/Sydney", ["en-AU", "en"]),
    "CA": ("America/Toronto", ["en-CA", "en", "fr-CA", "fr"]),
    "NL": ("Europe/Amsterdam", ["nl-NL", "nl", "en-US", "en"]),
    "JP": ("Asia/Tokyo", ["ja-JP", "ja", "en-US", "en"]),
    "AE": ("Asia/Dubai", ["en-AE", "en", "ar"]),
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


class FontContradictionError(RuntimeError):
    """Persona claims an OS whose fonts this host cannot rasterise."""


def build_persona(
    seed: str,
    proxy: str | None = None,
    caps: HostCaps | None = None,
) -> Persona:
    """
    Build one coherent identity.

    `caps` is the host font-capability probe. It is what stops us claiming an
    OS we cannot back up: `public/probe.js` measures fonts by real render
    width, so a persona may only claim an OS whose signature families actually
    rasterise on this machine. On a bare Linux container that means Windows and
    macOS personas are unavailable until the image ships real font packages --
    and macOS never becomes available, because Apple's fonts are not
    redistributable.
    """
    caps = assert_viable(caps)
    rng = random.Random(hashlib.sha256(seed.encode()).hexdigest())

    # Only consider devices whose OS this host can honestly impersonate.
    # _weighted_choice renormalises over whatever survives, so market-share
    # weighting is preserved within the viable subset.
    candidates = [p for p in DEVICE_PROFILES if p["os"] in caps.viable_os]
    if not candidates:
        raise FontContradictionError(
            "No device profile matches this host's viable OS set "
            f"({caps.viable_os or 'none'}).\n" + caps.report()
        )

    profile = _weighted_choice(rng, candidates)
    os_name = profile["os"]
    vendor, renderer = rng.choice(WEBGL_BY_OS[os_name])

    if SOFTWARE_RENDERER_PAT.search(renderer):
        raise ValueError(
            f"software renderer would be fatal to the scorer: {renderer!r}"
        )
    if DATACENTER_GPU_PAT.search(renderer):
        raise ValueError(
            f"datacenter GPU is not a consumer device: {renderer!r}"
        )

    # Font list: start from the OS base set, then keep ONLY families this host
    # can really render, so the claimed set equals the measurable set.
    base_fonts = caps.fonts_for(os_name, FONTS_BY_OS[os_name])

    # Real installs vary slightly, so drop a couple of *non-signature*
    # families. Signature families are never dropped: a Windows box missing
    # Arial is a bigger anomaly than one missing Gabriola.
    signature = {f.lower() for f in OS_SIGNATURE_FONTS.get(os_name, [])}
    droppable = [i for i, f in enumerate(base_fonts)
                 if f.lower() not in signature]
    drop = set(rng.sample(droppable, k=min(len(droppable), rng.randint(0, 4))))
    fonts = [f for i, f in enumerate(base_fonts) if i not in drop]

    # The scorer flags <= 2 measurable fonts (weight 25). Fail loudly here
    # rather than emitting a session that is guaranteed to be scored sparse.
    if len(fonts) <= 2:
        raise FontContradictionError(
            f"only {len(fonts)} of the {os_name} font set rasterise on this "
            "host; the scorer would flag this session as a container.\n"
            + caps.report()
        )

    geo = probe_proxy_geo(proxy) if proxy else {}
    country = geo.get("country")
    tz_default, locale_chain = GEO_DEFAULTS.get(
        country or "", ("Asia/Kolkata", ["en-IN", "en", "hi"])
    )
    timezone = geo.get("timezone") or tz_default
    locales = list(locale_chain)
    locale = locales[0]

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
        locales=locales,
        timezone=timezone,
        country=country,
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
        bias=bias,
    )


def outer_size(profile: dict) -> tuple[int, int]:
    """
    Outer window size derived from the inner size. Firefox has no side border,
    so outerWidth == innerWidth; vertically it adds the tab strip + nav bar.

    This is also what must be handed to Camoufox's `window=` launch argument:
    generate_fingerprint() documents that parameter as the *outer* size and
    routes it through handle_window_size(), which sets outerWidth/outerHeight
    directly. Passing the viewport there (as the launcher previously did) makes
    the OS window one chrome-height too short and desynchronises the real
    layout viewport from the spoofed innerHeight.
    """
    iw, ih = profile["viewport"]
    return iw, ih + FIREFOX_CHROME_PX[profile["os"]]


def validate_geometry(cfg: dict) -> None:
    """
    Fail loudly at build time rather than shipping an impossible window.

    Camoufox normally guards this itself via fix_screen_no_taskbar() and
    clamp_window_dimensions(), but utils.py gates both behind
    `if not _user_set_screen_window:` -- so the moment we override any
    screen.*/window.* key those safety nets switch off and whatever we inject
    is reported verbatim. We therefore have to assert the invariants ourselves.
    """
    for axis, w in (("Width", "width"), ("Height", "height")):
        screen = cfg[f"screen.{w}"]
        avail = cfg[f"screen.avail{axis}"]
        outer = cfg[f"window.outer{axis}"]
        inner = cfg[f"window.inner{axis}"]
        if not (inner <= outer <= avail <= screen):
            raise ValueError(
                f"impossible {axis.lower()} geometry: inner={inner} "
                f"outer={outer} avail={avail} screen={screen}"
            )

    # noTaskbar tell: some OS furniture must always be occupying space.
    if (cfg["screen.availWidth"] == cfg["screen.width"]
            and cfg["screen.availHeight"] == cfg["screen.height"]):
        raise ValueError("availWidth/Height equal screen -- noTaskbar tell")

    if cfg["window.outerWidth"] != cfg["window.innerWidth"]:
        raise ValueError("Firefox has no side border; outerWidth must equal "
                         "innerWidth")

    # Window must actually sit inside the screen.
    if (cfg["window.screenX"] + cfg["window.outerWidth"] > cfg["screen.width"]
            or cfg["window.screenY"] + cfg["window.outerHeight"]
            > cfg["screen.height"]):
        raise ValueError("window positioned partly off-screen")


def camoufox_config(p: Persona) -> dict:
    """
    Map a persona onto Camoufox's fingerprint override surface. Camoufox applies
    these inside the Firefox C++ source, so there is no JS-visible patch, no
    toString leak, and no property-descriptor anomaly to find.

    Key names are load-bearing. Camoufox's canonical screen keys are
    `screen.width`, `screen.availHeight`, ... (see browserforge.yml). The
    `window.screen.*` spelling used previously is not a recognised key, so the
    entire device screen profile was silently discarded and every persona fell
    back to a random BrowserForge screen unrelated to its own device identity.
    """
    sw, sh = p.profile["screen"]
    aw, ah = p.profile["avail"]
    iw, ih = p.profile["viewport"]
    ow, oh = outer_size(p.profile)
    al, at = p.profile["avail_origin"]

    if p.profile["maximized"]:
        sx, sy = al, at
    else:
        # Centred, the way a freshly dragged-out window sits.
        sx = max(al, (sw - ow) // 2)
        sy = max(at, (sh - oh) // 2)

    cfg = {
        "screen.width": sw,
        "screen.height": sh,
        "screen.availWidth": aw,
        "screen.availHeight": ah,
        "screen.availLeft": al,
        "screen.availTop": at,
        "screen.colorDepth": 24,
        "screen.pixelDepth": 24,
        "window.innerWidth": iw,
        "window.innerHeight": ih,
        "window.outerWidth": ow,
        "window.outerHeight": oh,
        "window.screenX": sx,
        "window.screenY": sy,
        "navigator.hardwareConcurrency": p.profile["cores"],
        "navigator.maxTouchPoints": p.profile["touch"],
        "webGl:vendor": p.webgl_vendor,
        "webGl:renderer": p.webgl_renderer,
        "fonts": p.fonts,
    }

    # Last line of defence. A Persona can be constructed directly (tests,
    # replayed seeds, a future scheduler), so re-assert the renderer rules at
    # the point the value actually reaches the browser.
    if SOFTWARE_RENDERER_PAT.search(p.webgl_renderer):
        raise ValueError(
            f"refusing to launch with software renderer {p.webgl_renderer!r} "
            "-- scorer treats this as fatal"
        )
    if DATACENTER_GPU_PAT.search(p.webgl_renderer):
        raise ValueError(
            f"refusing to launch with datacenter GPU {p.webgl_renderer!r} "
            "-- no consumer device reports this"
        )
    if len(p.fonts) <= 2:
        raise ValueError(
            f"refusing to launch with {len(p.fonts)} fonts -- scorer flags "
            "a sparse font set as a container tell"
        )

    validate_geometry(cfg)
    return cfg

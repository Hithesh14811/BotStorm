"""
Self-audit: run the checks the protector will run, against your own bot.

    python selftest.py

Never enter a round untested. This dumps the surface a detector inspects and
flags anything that would give you away, including the failure mode that most
anti-detect setups get wrong: unstable fingerprints. If canvas or audio hashes
change between two reads inside one session, that alone is conclusive -- real
hardware is deterministic, so differing hashes prove active tampering.
"""

from __future__ import annotations

import asyncio
import json
import random
import uuid

import persona as P

PROBE = r"""
() => {
  const out = {};
  const nav = navigator;

  // --- classic automation flags -----------------------------------------
  out.webdriver = nav.webdriver;
  out.hasCdcVars = Object.keys(window).filter(k =>
    /^\$?cdc_|^\$chrome_asyncScriptInfo|^__(webdriver|selenium|nightmare|playwright|puppeteer)/i.test(k));
  out.hasDocCdc = Object.keys(document).filter(k => /^\$?cdc_/.test(k));
  out.externalStr = (() => { try { return String(window.external); } catch(e){ return 'throws'; } })();

  // --- native-code integrity -------------------------------------------
  // JS-injection stealth plugins patch functions, and the patch is visible
  // here. Anything not ending in "{ [native code] }" is a red flag.
  const fns = {
    'Function.toString': Function.prototype.toString,
    'toDataURL': HTMLCanvasElement.prototype.toDataURL,
    'getContext': HTMLCanvasElement.prototype.getContext,
    'getImageData': (window.CanvasRenderingContext2D||{}).prototype?.getImageData,
    'getParameter': (window.WebGLRenderingContext||{}).prototype?.getParameter,
    'permissions.query': nav.permissions?.query,
    'getClientRects': Element.prototype.getClientRects,
    'AudioBuffer.getChannelData': (window.AudioBuffer||{}).prototype?.getChannelData,
  };
  out.nonNative = [];
  for (const [k, f] of Object.entries(fns)) {
    if (!f) continue;
    let s;
    try { s = Function.prototype.toString.call(f); } catch(e) { s = 'THROWS'; }
    if (!/\{\s*\[native code\]\s*\}$/.test(s)) out.nonNative.push(k);
  }

  // --- property descriptor anomalies ------------------------------------
  out.descriptorIssues = [];
  for (const key of ['webdriver','plugins','languages','platform','userAgent',
                     'hardwareConcurrency','deviceMemory']) {
    const d = Object.getOwnPropertyDescriptor(Navigator.prototype, key)
           || Object.getOwnPropertyDescriptor(nav, key);
    if (!d) { out.descriptorIssues.push(key + ':missing'); continue; }
    if (Object.prototype.hasOwnProperty.call(nav, key))
      out.descriptorIssues.push(key + ':own-property-on-instance');
  }

  // --- consistency ------------------------------------------------------
  out.ua = nav.userAgent;
  out.platform = nav.platform;
  out.languages = nav.languages;
  out.language = nav.language;
  out.cores = nav.hardwareConcurrency;
  out.memory = nav.deviceMemory;
  out.maxTouchPoints = nav.maxTouchPoints;
  out.pdfViewer = nav.pdfViewerEnabled;
  out.screen = { w: screen.width, h: screen.height,
                 aw: screen.availWidth, ah: screen.availHeight,
                 depth: screen.colorDepth };
  out.dpr = devicePixelRatio;
  out.inner = { w: innerWidth, h: innerHeight };
  out.outer = { w: outerWidth, h: outerHeight };
  out.tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
  out.tzOffset = new Date().getTimezoneOffset();
  out.pluginCount = nav.plugins?.length ?? null;
  out.mimeCount = nav.mimeTypes?.length ?? null;

  // outerHeight === 0 is the classic headless tell.
  out.zeroOuter = (outerWidth === 0 || outerHeight === 0);

  // --- WebGL ------------------------------------------------------------
  try {
    const c = document.createElement('canvas');
    const gl = c.getContext('webgl') || c.getContext('experimental-webgl');
    const dbg = gl.getExtension('WEBGL_debug_renderer_info');
    out.webgl = {
      vendor: gl.getParameter(gl.VENDOR),
      renderer: gl.getParameter(gl.RENDERER),
      unmaskedVendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
      unmaskedRenderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
    };
  } catch(e) { out.webgl = 'error: ' + e.message; }

  // --- canvas stability (read the SAME drawing twice) -------------------
  const drawHash = () => {
    const c = document.createElement('canvas');
    c.width = 240; c.height = 60;
    const ctx = c.getContext('2d');
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = '#f60'; ctx.fillRect(1, 1, 62, 20);
    ctx.fillStyle = '#069'; ctx.font = '11pt Arial';
    ctx.fillText('Cwm fjordbank glyphs vext quiz \u{1F600}', 2, 15);
    ctx.fillStyle = 'rgba(102,204,0,0.7)'; ctx.font = '18pt Arial';
    ctx.fillText('Cwm fjordbank glyphs vext quiz', 4, 45);
    const d = c.toDataURL();
    let h = 0;
    for (let i = 0; i < d.length; i++) h = ((h << 5) - h + d.charCodeAt(i)) | 0;
    return h;
  };
  out.canvasA = drawHash();
  out.canvasB = drawHash();
  out.canvasStable = out.canvasA === out.canvasB;

  // --- audio stability --------------------------------------------------
  out.audioStable = null;
  try {
    const run = () => {
      const Ctx = window.OfflineAudioContext || window.webkitOfflineAudioContext;
      const ctx = new Ctx(1, 4096, 44100);
      const osc = ctx.createOscillator();
      osc.type = 'triangle'; osc.frequency.value = 10000;
      const comp = ctx.createDynamicsCompressor();
      osc.connect(comp); comp.connect(ctx.destination); osc.start(0);
      return ctx.startRendering().then(buf => {
        const d = buf.getChannelData(0);
        let s = 0;
        for (let i = 2000; i < 3000; i++) s += Math.abs(d[i]);
        return s;
      });
    };
    return Promise.all([run(), run()]).then(([a, b]) => {
      out.audioA = a; out.audioB = b; out.audioStable = a === b;
      return out;
    });
  } catch(e) { out.audioStable = 'error'; }

  return out;
}
"""


PLATFORM_FOR_OS = {"windows": "Win32", "macos": "MacIntel", "linux": "Linux x86_64"}


def audit(fp: dict, per: P.Persona) -> list[str]:
    bad: list[str] = []

    if fp.get("webdriver") is True:
        bad.append("CRITICAL navigator.webdriver === true")
    if fp.get("hasCdcVars"):
        bad.append(f"CRITICAL automation globals leaked: {fp['hasCdcVars']}")
    if fp.get("hasDocCdc"):
        bad.append(f"CRITICAL document cdc_ keys: {fp['hasDocCdc']}")
    if fp.get("nonNative"):
        bad.append("CRITICAL non-native (patched) functions detectable: "
                   f"{fp['nonNative']} -- this is the signature of a JS "
                   "stealth plugin")
    if fp.get("descriptorIssues"):
        bad.append(f"WARN descriptor anomalies: {fp['descriptorIssues']}")
    if fp.get("zeroOuter"):
        bad.append("CRITICAL outerWidth/outerHeight is 0 (headless tell)")
    if fp.get("canvasStable") is False:
        bad.append("CRITICAL canvas hash UNSTABLE across two reads -- "
                   "randomised noise proves tampering")
    if fp.get("audioStable") is False:
        bad.append("CRITICAL audio fingerprint UNSTABLE across two reads")

    ua = (fp.get("ua") or "")
    if "Headless" in ua:
        bad.append("CRITICAL 'Headless' present in user-agent")

    want_platform = PLATFORM_FOR_OS.get(per.os)
    if want_platform and fp.get("platform") != want_platform:
        bad.append(f"WARN platform {fp.get('platform')!r} != expected "
                   f"{want_platform!r} for persona os {per.os}")

    sc = fp.get("screen") or {}
    if sc.get("w") and sc["w"] != per.profile["screen"][0]:
        bad.append(f"WARN screen width {sc.get('w')} != persona "
                   f"{per.profile['screen'][0]}")

    if fp.get("tz") != per.timezone:
        bad.append(f"WARN timezone {fp.get('tz')!r} != persona "
                   f"{per.timezone!r} (must match the proxy exit IP)")

    lang = fp.get("language") or ""
    if lang and per.locale and lang.split("-")[0] != per.locale.split("-")[0]:
        bad.append(f"WARN navigator.language {lang!r} vs locale {per.locale!r}")

    # navigator.languages must be the full persona chain AND its first element
    # must equal navigator.language. A browser where those two disagree does
    # not exist, so the mismatch is a zero-false-positive bot signal.
    langs = list(fp.get("languages") or [])
    if not langs:
        bad.append("CRITICAL navigator.languages is empty")
    elif langs != per.locales:
        bad.append(f"CRITICAL navigator.languages {langs} != persona chain "
                   f"{per.locales} -- Camoufox did not apply `locale:all`")
    elif lang and langs[0] != lang:
        bad.append(f"CRITICAL navigator.languages[0] {langs[0]!r} != "
                   f"navigator.language {lang!r}")

    wg = fp.get("webgl") or {}
    if isinstance(wg, dict):
        rend = (wg.get("unmaskedRenderer") or wg.get("renderer") or "")
        if per.os == "macos" and ("ANGLE" in rend or "Direct3D" in rend):
            bad.append(f"CRITICAL macOS persona with Windows GPU string: {rend!r}")
        if per.os == "windows" and rend.startswith("Apple"):
            bad.append(f"CRITICAL Windows persona with Apple GPU string: {rend!r}")
        if "SwiftShader" in rend or "llvmpipe" in rend:
            if per.os != "linux":
                bad.append(f"CRITICAL software renderer {rend!r} -- typical of "
                           "headless with no GPU")

    if fp.get("cores") and per.profile["cores"] != fp["cores"]:
        bad.append(f"WARN hardwareConcurrency {fp['cores']} != persona "
                   f"{per.profile['cores']}")

    return bad


async def main():
    from camoufox.async_api import AsyncCamoufox

    seed = str(uuid.uuid4())
    per = P.build_persona(seed, None)
    print(f"persona: {per.profile['name']} os={per.os} tz={per.timezone} "
          f"locale={per.locale}\n")

    # These launch arguments MUST be byte-for-byte what run.py uses, or the
    # audit certifies a browser you never actually ship:
    #   * `window=` is the OUTER size (see persona.outer_size), not the
    #     viewport. Passing the viewport here makes the real OS window one
    #     chrome-height too short, so documentElement.clientHeight disagrees
    #     with the spoofed innerHeight -- and the selftest would be measuring
    #     that broken geometry instead of the real one.
    #   * `locale=` must be the full LIST. Camoufox's handle_locales() returns
    #     early on a single-element list and never populates `locale:all`, so
    #     navigator.languages keeps whatever the random fingerprint had and can
    #     contradict navigator.language. Auditing with a bare string therefore
    #     hides the exact inconsistency the audit exists to catch.
    ow, oh = P.outer_size(per.profile)
    async with AsyncCamoufox(
        headless=False,
        geoip=False,
        humanize=False,
        locale=per.locales,
        os=[per.os],
        config=P.camoufox_config(per),
        window=(ow, oh),
        block_webrtc=True,
        i_know_what_im_doing=True,
    ) as browser:
        page = await browser.new_page()
        await page.goto("about:blank")
        # A real origin: some APIs behave differently on about:blank.
        await page.set_content("<!doctype html><title>t</title><h1>selftest</h1>")
        fp = await page.evaluate(PROBE)

    print(json.dumps(fp, indent=2, default=str)[:4000])
    print("\n--- AUDIT ---")
    issues = audit(fp, per)
    if not issues:
        print("clean: no leaks found by these checks.")
    for i in issues:
        print(" -", i)
    crit = [i for i in issues if i.startswith("CRITICAL")]
    print(f"\n{len(crit)} critical, {len(issues) - len(crit)} warnings.")


if __name__ == "__main__":
    asyncio.run(main())

/* ------------------------------------------------------------------
 * probe.js -- adversarial telemetry collector.
 *
 * This is the RED TEAM'S MIRROR. It implements the signals a serious
 * anti-fraud engineer collects, so you can measure your own bot before
 * your opponent measures it for you.
 *
 * Round 1: run your bot against this, drive the score down.
 * Round 2: this file, plus scoring, becomes your defence.
 *
 * Deliberately NOT obfuscated -- you need to read it to learn from it.
 * ------------------------------------------------------------------ */
(function () {
  "use strict";

  var T0 = performance.now();
  var ev = {
    move: [],      // [t, x, y]
    down: [],      // [t, x, y, button]
    up: [],
    click: [],
    key: [],       // [t, type, code, isTrusted]
    wheel: [],     // [t, dy, mode]
    scroll: [],
    focus: [],
    vis: [],
  };
  var CAP = 4000;
  function push(a, v) { if (a.length < CAP) a.push(v); }
  var now = function () { return +(performance.now() - T0).toFixed(2); };

  /* ---------- behavioural capture ---------- */
  addEventListener("mousemove", function (e) {
    push(ev.move, [now(), e.clientX, e.clientY, e.isTrusted ? 1 : 0]);
  }, { passive: true, capture: true });

  addEventListener("mousedown", function (e) {
    push(ev.down, [now(), e.clientX, e.clientY, e.button, e.isTrusted ? 1 : 0]);
  }, { passive: true, capture: true });

  addEventListener("mouseup", function (e) {
    push(ev.up, [now(), e.clientX, e.clientY, e.isTrusted ? 1 : 0]);
  }, { passive: true, capture: true });

  addEventListener("click", function (e) {
    push(ev.click, [now(), e.clientX, e.clientY, e.isTrusted ? 1 : 0,
                    e.detail, (e.target && e.target.tagName) || "?"]);
  }, { passive: true, capture: true });

  ["keydown", "keyup"].forEach(function (t) {
    addEventListener(t, function (e) {
      push(ev.key, [now(), t === "keydown" ? "d" : "u", e.code || e.key,
                    e.isTrusted ? 1 : 0]);
    }, { passive: true, capture: true });
  });

  addEventListener("wheel", function (e) {
    push(ev.wheel, [now(), +e.deltaY.toFixed(2), e.deltaMode,
                    e.isTrusted ? 1 : 0]);
  }, { passive: true, capture: true });

  addEventListener("scroll", function () {
    push(ev.scroll, [now(), Math.round(scrollY)]);
  }, { passive: true, capture: true });

  ["focus", "blur"].forEach(function (t) {
    addEventListener(t, function () { push(ev.focus, [now(), t]); }, true);
  });
  addEventListener("visibilitychange", function () {
    push(ev.vis, [now(), document.visibilityState]);
  });

  /* ---------- environment / fingerprint surface ---------- */
  function canvasHash() {
    try {
      var c = document.createElement("canvas");
      c.width = 220; c.height = 60;
      var g = c.getContext("2d");
      g.textBaseline = "top";
      g.font = "16px 'Arial'";
      g.fillStyle = "#f60"; g.fillRect(0, 0, 110, 30);
      g.fillStyle = "#069"; g.fillText("Cwm fjord bank glyphs, \u{1F600}", 2, 2);
      g.fillStyle = "rgba(102,204,0,0.7)";
      g.fillText("Cwm fjord bank glyphs", 4, 20);
      g.globalCompositeOperation = "multiply";
      g.beginPath(); g.arc(50, 50, 25, 0, Math.PI * 2); g.fill();
      var d = c.toDataURL();
      var h = 5381;
      for (var i = 0; i < d.length; i++) h = ((h << 5) + h + d.charCodeAt(i)) | 0;
      return h.toString(16);
    } catch (e) { return "err:" + e.name; }
  }

  function webgl() {
    try {
      var c = document.createElement("canvas");
      var g = c.getContext("webgl") || c.getContext("experimental-webgl");
      if (!g) return { ok: false };
      var dbg = g.getExtension("WEBGL_debug_renderer_info");
      return {
        ok: true,
        vendor: g.getParameter(g.VENDOR),
        renderer: g.getParameter(g.RENDERER),
        uVendor: dbg ? g.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : null,
        uRenderer: dbg ? g.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : null,
        maxTex: g.getParameter(g.MAX_TEXTURE_SIZE),
        exts: (g.getSupportedExtensions() || []).length,
      };
    } catch (e) { return { ok: false, err: e.name }; }
  }

  /* Automation tells. This is the part naive stealth plugins fail. */
  function automationTells() {
    var t = {};
    t.webdriver = navigator.webdriver === true;

    // CDP / driver-injected globals.
    var keys = ["__webdriver_evaluate", "__selenium_evaluate", "__driver_evaluate",
      "__webdriver_script_fn", "__fxdriver_evaluate", "__driver_unwrapped",
      "_Selenium_IDE_Recorder", "callSelenium", "_selenium",
      "cdc_adoQpoasnfa76pfcZLmcfl_Array", "cdc_adoQpoasnfa76pfcZLmcfl_Promise",
      "__nightmare", "__phantomas", "_phantom", "callPhantom",
      "domAutomation", "domAutomationController", "__pw_manual",
      "__playwright", "__puppeteer_evaluation_script__"];
    t.injectedGlobals = keys.filter(function (k) {
      try { return k in window || k in document; } catch (e) { return false; }
    });

    // Native-code integrity: patched functions stop looking native.
    function nativeish(fn) {
      try { return /\{\s*\[native code\]\s*\}/.test(Function.prototype.toString.call(fn)); }
      catch (e) { return false; }
    }
    t.patched = [];
    [["Function.toString", Function.prototype.toString],
     ["permissions.query", navigator.permissions && navigator.permissions.query],
     ["getParameter", window.WebGLRenderingContext &&
        WebGLRenderingContext.prototype.getParameter],
     ["toDataURL", HTMLCanvasElement.prototype.toDataURL],
     ["getImageData", window.CanvasRenderingContext2D &&
        CanvasRenderingContext2D.prototype.getImageData],
     ["getClientRects", Element.prototype.getClientRects],
     ["Date.getTimezoneOffset", Date.prototype.getTimezoneOffset],
    ].forEach(function (p) {
      if (p[1] && !nativeish(p[1])) t.patched.push(p[0]);
    });

    // Property descriptors on navigator: spoofs often leave own props
    // where the real thing has prototype getters.
    t.ownNavProps = ["webdriver", "languages", "plugins", "platform",
      "hardwareConcurrency", "deviceMemory", "userAgent"]
      .filter(function (k) {
        return Object.prototype.hasOwnProperty.call(navigator, k);
      });

    // Consistency: UA vs platform vs client hints vs touch.
    var ua = navigator.userAgent;
    t.ua = ua;
    t.platform = navigator.platform;
    t.uaMobile = /Mobi|Android|iPhone/.test(ua);
    t.maxTouch = navigator.maxTouchPoints;
    t.touchMismatch = t.uaMobile !== (navigator.maxTouchPoints > 0);
    var claimsMac = /Mac OS X/.test(ua), claimsWin = /Windows/.test(ua),
        claimsLin = /Linux|X11/.test(ua) && !/Android/.test(ua);
    var p = (navigator.platform || "");
    t.platformMismatch =
      (claimsMac && !/Mac/.test(p)) ||
      (claimsWin && !/Win/.test(p)) ||
      (claimsLin && !/Linux|arm|aarch/i.test(p));

    // Headless heuristics.
    t.headlessUA = /HeadlessChrome/.test(ua);
    t.zeroDims = !(outerWidth > 0 && outerHeight > 0);
    t.chromeMissing = /Chrome\//.test(ua) && !window.chrome;
    t.noPlugins = (navigator.plugins || []).length === 0;
    t.pdfViewer = navigator.pdfViewerEnabled;
    t.langsEmpty = !(navigator.languages || []).length;

    // Timezone vs Accept-Language coherence is checked server side; report raw.
    try {
      t.tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
      t.tzOffset = new Date().getTimezoneOffset();
    } catch (e) { t.tz = null; }

    // Notification/permission inconsistency (classic headless tell).
    t.permissionAnomaly = null;
    return t;
  }

  async function permissionProbe() {
    try {
      if (!navigator.permissions || !navigator.permissions.query) return null;
      var st = await navigator.permissions.query({ name: "notifications" });
      return { state: st.state, notif: (window.Notification || {}).permission };
    } catch (e) { return { err: e.name }; }
  }

  function envSnapshot() {
    return {
      screen: [screen.width, screen.height, screen.availWidth,
               screen.availHeight, screen.colorDepth],
      dpr: devicePixelRatio,
      viewport: [innerWidth, innerHeight],
      outer: [outerWidth, outerHeight],
      cores: navigator.hardwareConcurrency,
      mem: navigator.deviceMemory || null,
      langs: navigator.languages,
      lang: navigator.language,
      cookieEnabled: navigator.cookieEnabled,
      dnt: navigator.doNotTrack,
      touch: navigator.maxTouchPoints,
      plugins: Array.prototype.map.call(navigator.plugins || [],
                                       function (x) { return x.name; }),
      mimeTypes: (navigator.mimeTypes || []).length,
      canvas: canvasHash(),
      webgl: webgl(),
      // Font presence via measurement -- a real OS has a distinct font set.
      fonts: (function () {
        var probe = ["Arial", "Times New Roman", "Courier New", "Segoe UI",
          "Helvetica Neue", "Ubuntu", "Cantarell", "DejaVu Sans",
          "Liberation Sans", "Tahoma", "Verdana", "Georgia"];
        var s = document.createElement("span");
        s.style.cssText = "position:absolute;left:-9999px;font-size:72px";
        s.textContent = "mmmmmmmmmmlli";
        document.body.appendChild(s);
        s.style.fontFamily = "monospace";
        var base = s.offsetWidth;
        var found = probe.filter(function (f) {
          s.style.fontFamily = "'" + f + "',monospace";
          return s.offsetWidth !== base;
        });
        s.remove();
        return found;
      })(),
      // Media/codec surface differs in headless builds.
      codecs: (function () {
        try {
          var v = document.createElement("video");
          return {
            h264: v.canPlayType('video/mp4; codecs="avc1.42E01E"'),
            webm: v.canPlayType('video/webm; codecs="vp9"'),
            ogg: v.canPlayType("video/ogg"),
          };
        } catch (e) { return null; }
      })(),
      audioCtx: (function () {
        try {
          var AC = window.AudioContext || window.webkitAudioContext;
          if (!AC) return null;
          var c = new AC();
          var r = { rate: c.sampleRate, ch: c.destination.maxChannelCount,
                    state: c.state };
          if (c.close) c.close();
          return r;
        } catch (e) { return null; }
      })(),
    };
  }

  /* ---------- honeypot instrumentation ---------- */
  var trapHits = [];
  function armTraps() {
    document.querySelectorAll("[data-trap]").forEach(function (el) {
      var name = el.getAttribute("data-trap");
      ["click", "focus", "input", "change", "mouseover"].forEach(function (t) {
        el.addEventListener(t, function () {
          trapHits.push({ trap: name, type: t, t: now() });
        }, { capture: true });
      });
    });
  }
  if (document.readyState === "loading") {
    addEventListener("DOMContentLoaded", armTraps);
  } else { armTraps(); }

  /* ---------- report ---------- */
  async function build() {
    var tells = automationTells();
    tells.permissionAnomaly = await permissionProbe();
    return {
      sid: (function () {
        var k = "probe_sid", v = sessionStorage.getItem(k);
        if (!v) {
          v = (crypto.randomUUID ? crypto.randomUUID()
                                 : String(Math.random()).slice(2));
          sessionStorage.setItem(k, v);
        }
        return v;
      })(),
      url: location.pathname,
      duration: now(),
      nav: (function () {
        var n = performance.getEntriesByType("navigation")[0];
        return n ? { type: n.type, ttfb: +n.responseStart.toFixed(1),
                     dcl: +n.domContentLoadedEventEnd.toFixed(1) } : null;
      })(),
      env: envSnapshot(),
      tells: tells,
      traps: trapHits,
      counts: {
        move: ev.move.length, down: ev.down.length, up: ev.up.length,
        click: ev.click.length, key: ev.key.length,
        wheel: ev.wheel.length, scroll: ev.scroll.length,
      },
      ev: ev,
    };
  }

  async function send(reason) {
    try {
      var body = JSON.stringify({ reason: reason, report: await build() });
      // keepalive so the unload-time POST actually leaves the browser.
      await fetch("/api/collect", {
        method: "POST", keepalive: true,
        headers: { "content-type": "application/json" },
        body: body,
      });
    } catch (e) { /* never break the page */ }
  }

  window.__probe = { build: build, send: send, ev: ev };

  // Report on exit AND on a timer, so we capture sessions that never unload.
  addEventListener("pagehide", function () { send("pagehide"); });
  addEventListener("beforeunload", function () { send("beforeunload"); });
  setTimeout(function () { send("timer-15s"); }, 15000);
  setTimeout(function () { send("timer-45s"); }, 45000);
})();

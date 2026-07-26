/**
 * score.ts -- adversarial session scorer.
 *
 * Implements the tests a competent anti-fraud engineer runs on a raw event
 * stream. Every check returns a weighted signal plus a human-readable reason,
 * so you can see EXACTLY which behaviour betrayed the bot.
 *
 * Score is 0 (indistinguishable from human) .. 100 (certainly automated).
 * Treat anything above ~25 as a likely fail in a strict round.
 */

export type Report = {
  sid: string
  url?: string
  duration: number
  nav?: { type: string; ttfb: number; dcl: number } | null
  env: Record<string, any>
  tells: Record<string, any>
  traps: Array<{ trap: string; type: string; t: number }>
  counts: Record<string, number>
  ev: {
    move: number[][]
    down: number[][]
    up: number[][]
    click: any[][]
    key: any[][]
    wheel: number[][]
    scroll: number[][]
    focus: any[][]
    vis: any[][]
  }
}

export type Signal = {
  id: string
  label: string
  weight: number // contribution added to score
  detail: string
  severity: "info" | "warn" | "fatal"
}

/* ------------------------- small stats helpers ------------------------- */

const mean = (a: number[]) => (a.length ? a.reduce((s, x) => s + x, 0) / a.length : 0)

function sd(a: number[]) {
  if (a.length < 2) return 0
  const m = mean(a)
  return Math.sqrt(a.reduce((s, x) => s + (x - m) ** 2, 0) / a.length)
}

/** Coefficient of variation — scale-free dispersion. Humans are messy. */
function cv(a: number[]) {
  const m = mean(a)
  return m === 0 ? 0 : sd(a) / m
}

/**
 * Benford-style first-digit test is overkill here; instead we test for
 * quantisation: synthetic timings often land on suspiciously few distinct
 * values, or on exact multiples of a base unit.
 */
function quantisation(a: number[]) {
  if (a.length < 8) return { distinctRatio: 1, gridHit: 0 }
  const r = a.map((x) => Math.round(x * 1000))
  const distinctRatio = new Set(r).size / r.length
  let best = 0
  for (const unit of [1, 2, 4, 5, 8, 10, 16, 20, 25, 50, 100]) {
    const hit = r.filter((x) => x % unit === 0).length / r.length
    if (unit > 1 && hit > best) best = hit
  }
  return { distinctRatio, gridHit: best }
}

/** Shannon entropy of a value histogram, normalised 0..1. */
function entropy(vals: number[], bins = 16) {
  if (vals.length < 4) return 1
  const lo = Math.min(...vals)
  const hi = Math.max(...vals)
  if (hi === lo) return 0
  const h = new Array(bins).fill(0)
  for (const v of vals) {
    const i = Math.min(bins - 1, Math.floor(((v - lo) / (hi - lo)) * bins))
    h[i]++
  }
  let e = 0
  for (const c of h) {
    if (c) {
      const p = c / vals.length
      e -= p * Math.log2(p)
    }
  }
  return e / Math.log2(bins)
}

/** Autocorrelation at lag 1 — periodic bots show structure. */
function acf1(a: number[]) {
  if (a.length < 8) return 0
  const m = mean(a)
  let num = 0
  let den = 0
  for (let i = 0; i < a.length; i++) {
    den += (a[i] - m) ** 2
    if (i) num += (a[i] - m) * (a[i - 1] - m)
  }
  return den === 0 ? 0 : num / den
}

/* ------------------------------ the scorer ----------------------------- */

export function scoreSession(r: Report): { score: number; signals: Signal[] } {
  const S: Signal[] = []
  const add = (
    id: string,
    label: string,
    weight: number,
    detail: string,
    severity: Signal["severity"] = "warn",
  ) => S.push({ id, label, weight, detail, severity })

  const t = r.tells || {}
  const env = r.env || {}
  const ev = r.ev || ({} as Report["ev"])

  /* ===================== 1. HARD AUTOMATION TELLS ===================== */

  if (t.webdriver) add("webdriver", "navigator.webdriver is true", 100, "The browser self-identifies as automated.", "fatal")

  if (t.injectedGlobals?.length)
    add(
      "globals",
      "Driver globals present",
      100,
      `Found: ${t.injectedGlobals.join(", ")}`,
      "fatal",
    )

  if (t.headlessUA) add("headless-ua", "HeadlessChrome in UA", 100, String(t.ua), "fatal")

  /* The stealth-plugin killer: patched natives. */
  if (t.patched?.length)
    add(
      "patched-natives",
      "Non-native function bodies",
      Math.min(80, 26 * t.patched.length),
      `Patched: ${t.patched.join(", ")}. Real browsers return "[native code]". ` +
        `This is how spoofing libraries are caught even when their values look perfect.`,
      "fatal",
    )

  if (t.ownNavProps?.length)
    add(
      "nav-descriptors",
      "Own properties on navigator",
      Math.min(45, 15 * t.ownNavProps.length),
      `${t.ownNavProps.join(", ")} are own props; genuine ones live on the prototype.`,
      "fatal",
    )

  /* ===================== 2. ENVIRONMENT COHERENCE ===================== */

  if (t.platformMismatch) add("platform", "UA/platform mismatch", 55, `UA says one OS, navigator.platform says "${t.platform}".`, "fatal")
  if (t.touchMismatch) add("touch", "Touch capability mismatch", 35, `maxTouchPoints=${t.maxTouch} contradicts the UA form factor.`)
  if (t.chromeMissing) add("chrome-obj", "Chrome UA without window.chrome", 45, "Claims Chrome but the chrome object is absent.", "fatal")
  if (t.zeroDims) add("dims", "Zero outer dimensions", 40, "outerWidth/Height are 0 — typical of headless.", "fatal")
  if (t.langsEmpty) add("langs", "Empty navigator.languages", 30, "Real browsers always expose at least one language.")

  const wg = env.webgl || {}
  if (!wg.ok) {
    add("webgl", "No WebGL context", 30, "Most real desktop browsers provide WebGL.")
  } else if (/SwiftShader|llvmpipe|Mesa OffScreen|Software/i.test(String(wg.uRenderer || wg.renderer))) {
    add("swiftshader", "Software renderer", 40, `renderer="${wg.uRenderer || wg.renderer}" indicates no real GPU — a strong headless signal.`, "fatal")
  }

  if (Array.isArray(env.fonts) && env.fonts.length <= 2)
    add("fonts", "Sparse font set", 25, `Only ${env.fonts.length} probe fonts present — containers lack real OS fonts.`)

  if (env.cores && (env.cores < 2 || env.cores > 32))
    add("cores", "Implausible core count", 12, `hardwareConcurrency=${env.cores}.`, "info")

  if (Array.isArray(env.screen) && Array.isArray(env.viewport)) {
    const [sw, sh] = env.screen
    const [vw, vh] = env.viewport
    if (vw > sw || vh > sh) add("viewport", "Viewport exceeds screen", 35, `viewport ${vw}x${vh} > screen ${sw}x${sh} — impossible.`, "fatal")
    if (sw === vw && sh === vh) add("chromeless", "No browser chrome", 18, "Viewport exactly equals screen; real windows have toolbars.")
  }

  if (env.audioCtx?.rate && ![44100, 48000, 96000].includes(env.audioCtx.rate))
    add("audio", "Unusual audio sample rate", 10, `sampleRate=${env.audioCtx.rate}.`, "info")

  /* ========================= 3. HONEYPOTS ============================= */

  if (r.traps?.length) {
    const names = [...new Set(r.traps.map((x) => x.trap))]
    add(
      "honeypot",
      "Honeypot interaction",
      100,
      `Touched hidden element(s): ${names.join(", ")}. No sighted human can do this. ` +
        `Zero false positives — this is the cheapest, deadliest check in the book.`,
      "fatal",
    )
  }

  /* ==================== 4. INPUT PRESENCE / TRUST ===================== */

  const moves = ev.move || []
  const clicks = ev.click || []
  const keys = ev.key || []
  const wheels = ev.wheel || []

  const untrusted =
    moves.filter((m) => m[3] === 0).length +
    clicks.filter((c) => c[3] === 0).length +
    keys.filter((k) => k[3] === 0).length +
    wheels.filter((w) => w[3] === 0).length

  if (untrusted > 0)
    add(
      "untrusted",
      "Synthetic (untrusted) events",
      100,
      `${untrusted} events had isTrusted=false — dispatched by script, not by the input stack. ` +
        `This is why real input injection (CDP/driver-level) beats JS event dispatch.`,
      "fatal",
    )

  if (r.duration > 4000 && moves.length === 0 && clicks.length > 0)
    add("teleport-click", "Clicks without any movement", 70, "Pointer reached targets without traversing the page.", "fatal")

  if (r.duration > 8000 && moves.length === 0 && wheels.length === 0 && keys.length === 0)
    add("inert", "No human input at all", 60, `${(r.duration / 1000).toFixed(1)}s on page with zero interaction.`)

  /* ==================== 5. MOUSE KINEMATICS =========================== */

  if (moves.length >= 12) {
    const dt: number[] = []
    const speed: number[] = []
    const dxs: number[] = []
    const dys: number[] = []
    for (let i = 1; i < moves.length; i++) {
      const d = moves[i][0] - moves[i - 1][0]
      const dx = moves[i][1] - moves[i - 1][1]
      const dy = moves[i][2] - moves[i - 1][2]
      if (d > 0 && d < 400) {
        dt.push(d)
        speed.push(Math.hypot(dx, dy) / d)
        dxs.push(dx)
        dys.push(dy)
      }
    }

    if (dt.length >= 10) {
      // (a) Perfectly regular sampling => scripted stepping.
      const c = cv(dt)
      if (c < 0.12) add("move-regular", "Metronomic mousemove timing", 45, `CV of inter-move gaps = ${c.toFixed(3)}. Human pointer sampling jitters far more.`, "fatal")
      else if (c < 0.22) add("move-regular", "Suspiciously even mousemove timing", 18, `CV = ${c.toFixed(3)}.`)

      const q = quantisation(dt.map((x) => x / 1000))
      if (q.distinctRatio < 0.25) add("move-quant", "Quantised move timings", 30, `Only ${(q.distinctRatio * 100).toFixed(0)}% distinct gap values.`)
      if (q.gridHit > 0.9) add("move-grid", "Move timings on a fixed grid", 28, `${(q.gridHit * 100).toFixed(0)}% of gaps are exact multiples of one unit.`)

      // (b) Velocity profile: human aimed motion accelerates then decelerates.
      const third = Math.floor(speed.length / 3)
      if (third >= 3) {
        const a = mean(speed.slice(0, third))
        const b = mean(speed.slice(third, 2 * third))
        const cc = mean(speed.slice(2 * third))
        if (!(b > a && b > cc) && speed.length > 20) {
          add("no-bell", "No ballistic velocity profile", 22, `Segment speeds ${a.toFixed(2)}/${b.toFixed(2)}/${cc.toFixed(2)} — genuine aimed movement peaks mid-flight.`)
        }
      }

      // (c) Straightness: a perfectly linear path is a dead giveaway.
      const totalPath = speed.reduce((s, v, i) => s + v * dt[i], 0)
      const net = Math.hypot(
        moves[moves.length - 1][1] - moves[0][1],
        moves[moves.length - 1][2] - moves[0][2],
      )
      if (net > 120 && totalPath > 0) {
        const straight = net / totalPath
        if (straight > 0.985) add("linear", "Pixel-perfect straight path", 40, `Path efficiency ${straight.toFixed(4)} — humans overshoot and correct.`, "fatal")
      }

      // (d) Entropy of step sizes.
      const eX = entropy(dxs)
      const eY = entropy(dys)
      if (Math.min(eX, eY) < 0.25) add("move-entropy", "Low movement entropy", 25, `Step-size entropy X=${eX.toFixed(2)} Y=${eY.toFixed(2)}.`)

      // (e) Autocorrelation: procedural generators leave periodicity.
      const ac = acf1(dt)
      if (Math.abs(ac) > 0.75) add("move-acf", "Periodic movement structure", 20, `lag-1 autocorrelation = ${ac.toFixed(2)}.`)
    }
  }

  /* ==================== 6. KEYSTROKE DYNAMICS ========================= */

  const downs = keys.filter((k) => k[1] === "d")
  if (downs.length >= 8) {
    const gaps: number[] = []
    for (let i = 1; i < downs.length; i++) {
      const g = downs[i][0] - downs[i - 1][0]
      if (g > 0 && g < 3000) gaps.push(g)
    }
    if (gaps.length >= 6) {
      const c = cv(gaps)
      if (c < 0.15) add("key-regular", "Metronomic typing", 50, `Digraph-latency CV = ${c.toFixed(3)}. Human typing varies hugely by letter pair.`, "fatal")
      else if (c < 0.28) add("key-regular", "Low typing variance", 20, `CV = ${c.toFixed(3)}.`)

      const q = quantisation(gaps.map((x) => x / 1000))
      if (q.gridHit > 0.9) add("key-grid", "Keystroke gaps on a grid", 30, `${(q.gridHit * 100).toFixed(0)}% are multiples of one unit — a fixed delay() loop.`)

      if (mean(gaps) < 35) add("key-fast", "Superhuman typing speed", 35, `Mean gap ${mean(gaps).toFixed(0)}ms (~${(12000 / mean(gaps)).toFixed(0)} WPM).`, "fatal")

      // Dwell time (down->up on same key) is a strong biometric.
      const dwells: number[] = []
      for (const d of downs) {
        const u = keys.find((k) => k[1] === "u" && k[2] === d[2] && k[0] > d[0])
        if (u) {
          const w = u[0] - d[0]
          if (w > 0 && w < 500) dwells.push(w)
        }
      }
      if (dwells.length >= 6) {
        if (sd(dwells) < 3) add("dwell", "Constant key dwell time", 30, `Dwell sd=${sd(dwells).toFixed(1)}ms — real key presses vary.`)
        if (mean(dwells) < 12) add("dwell-fast", "Implausibly short dwell", 20, `Mean dwell ${mean(dwells).toFixed(1)}ms.`)
      }

      const hasCorrections = keys.some((k) => /Backspace/.test(String(k[2])))
      if (gaps.length > 25 && !hasCorrections)
        add("no-typos", "Long flawless typing run", 10, "No corrections across a long input — unusual for free-text entry.", "info")
    }
  }

  /* ==================== 7. SCROLL / WHEEL PHYSICS ===================== */

  if (wheels.length >= 5) {
    const deltas = wheels.map((w) => Math.abs(w[1]))
    const uniq = [...new Set(deltas)]

    // A real wheel emits integer multiples of one notch unit.
    const notchy = uniq.every((d) => d % 100 === 0) || uniq.every((d) => d % 120 === 0)
    const pixelMode = wheels.every((w) => w[2] === 0)

    if (uniq.length === 1 && wheels.length > 10)
      add("wheel-const", "Single repeated wheel delta", 22, `Every event deltaY=${uniq[0]} with no variation across ${wheels.length} events.`)

    if (!pixelMode) add("wheel-mode", "Non-pixel deltaMode", 12, "deltaMode differs from the browser default.", "info")

    if (!notchy && uniq.length > 3) {
      const frac = deltas.filter((d) => !Number.isInteger(d)).length
      if (frac > deltas.length * 0.5)
        add("wheel-frac", "Fractional wheel deltas", 26, `${frac}/${deltas.length} deltas are non-integer. A detented wheel cannot emit these; only trackpads come close, and they use small values.`)
    }

    const gaps: number[] = []
    for (let i = 1; i < wheels.length; i++) {
      const g = wheels[i][0] - wheels[i - 1][0]
      if (g > 0 && g < 2000) gaps.push(g)
    }
    if (gaps.length >= 6 && cv(gaps) < 0.1)
      add("wheel-regular", "Metronomic wheel timing", 30, `CV = ${cv(gaps).toFixed(3)}.`)
  }

  const scrolls = ev.scroll || []
  if (scrolls.length >= 4) {
    const ys = scrolls.map((s) => s[1])
    const monotone = ys.every((y, i) => i === 0 || y >= ys[i - 1])
    if (monotone && ys.length > 12 && ys[ys.length - 1] > 800)
      add("scroll-monotone", "Never scrolled back", 12, "Humans reading long pages usually scroll up at least once.", "info")
  }

  /* ==================== 8. SESSION SHAPE ============================== */

  if (r.duration < 9500) add("too-short", "Session under the 10s floor", 45, `Only ${(r.duration / 1000).toFixed(1)}s on page — violates the dwell requirement.`, "fatal")
  if (r.duration > 61000) add("too-long", "Session over the 60s ceiling", 25, `${(r.duration / 1000).toFixed(1)}s on page.`)

  if (!r.ev.focus?.length && r.duration > 15000)
    add("no-focus", "No focus/blur activity", 8, "Real users switch away at least occasionally.", "info")

  /* --------------------------- aggregate ----------------------------- */

  // Saturating sum: many weak signals should build confidence without a
  // single medium signal being able to max the score on its own.
  const total = S.reduce((s, x) => s + x.weight, 0)
  const score = Math.round(100 * (1 - Math.exp(-total / 55)))

  S.sort((a, b) => b.weight - a.weight)
  return { score: Math.min(100, score), signals: S }
}

export function verdict(score: number) {
  if (score >= 70) return { label: "BOT — blocked", tone: "bad" as const }
  if (score >= 40) return { label: "Likely bot — challenged", tone: "bad" as const }
  if (score >= 25) return { label: "Suspicious — flagged", tone: "warn" as const }
  if (score >= 10) return { label: "Probably human", tone: "ok" as const }
  return { label: "Human — passed", tone: "ok" as const }
}

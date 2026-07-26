/**
 * The honeypot battery.
 *
 * Design principle that makes this a real test: every trap is given a
 * PLAUSIBLE, INNOCUOUS name -- `email`, `phone`, `message`, `full_name`. A bot
 * that decides what to fill by pattern-matching field names (which is exactly
 * what bot/safety.py's plausible_value() does) will happily fill all of them.
 * The only thing that saves it is refusing to touch elements a human eye
 * cannot see.
 *
 * So this file does not test "can the bot spot the word honeypot". It tests
 * whether the bot's visibility model is correct. That is the check a real
 * ad-fraud engineer writes first, because it has a zero false-positive rate:
 * no sighted human can fill a field that is not rendered.
 *
 * Each trap is hidden by a DIFFERENT mechanism, because a bot that only checks
 * `display:none` passes trap 1 and dies on trap 6. The list is ordered roughly
 * easiest -> subtlest.
 *
 * `data-trap` is the attribute public/probe.js arms listeners on.
 */

// Hidden from assistive tech too, so a screen-reader user is never trapped
// either -- a real defender must do this or the honeypot becomes a bug.
const A11Y = { "aria-hidden": true as const, tabIndex: -1 }

export function Honeypots() {
  return (
    <>
      {/* 1. display:none -- the classic. Anything that enumerates
             querySelectorAll('input') without a style check dies here. */}
      <div style={{ display: "none" }} {...A11Y}>
        <label htmlFor="hp-email">Email</label>
        <input id="hp-email" name="email" type="email" data-trap="display-none" autoComplete="off" />
      </div>

      {/* 2. visibility:hidden -- still occupies layout, so getBoundingClientRect
             returns a NON-zero box. A bot that only rejects zero-size elements
             is caught by exactly this. */}
      <div style={{ visibility: "hidden", height: 40 }} {...A11Y}>
        <label htmlFor="hp-phone">Phone</label>
        <input id="hp-phone" name="phone" type="tel" data-trap="visibility-hidden" autoComplete="off" />
      </div>

      {/* 3. opacity:0 -- fully laid out, fully sized, fully invisible. */}
      <div style={{ opacity: 0, height: 40 }} {...A11Y}>
        <label htmlFor="hp-company">Company</label>
        <input id="hp-company" name="company" data-trap="opacity-zero" autoComplete="off" />
      </div>

      {/* 4. Parked off-screen in document space. Note this is NOT merely below
             the fold -- a correct probe must distinguish "off-screen" from
             "not scrolled to yet", or it will refuse to fill legitimate fields
             further down the page. */}
      <div style={{ position: "absolute", left: -9999, top: "auto" }} {...A11Y}>
        <label htmlFor="hp-name">Full name</label>
        <input id="hp-name" name="full_name" data-trap="offscreen-left" autoComplete="off" />
      </div>

      {/* 5. Collapsed to 1x1 with hidden overflow. */}
      <div style={{ width: 1, height: 1, overflow: "hidden" }} {...A11Y}>
        <input name="subject" data-trap="one-by-one" autoComplete="off" />
      </div>

      {/* 6. clip-path: inset(100%) -- the modern sr-only idiom. Renders,
             occupies layout, has a real box, is completely unpainted.
             getComputedStyle().display/visibility/opacity all look NORMAL.
             This is the trap that catches most "good" bots. */}
      <div style={{ clipPath: "inset(100%)", position: "absolute", width: 240, height: 40 }} {...A11Y}>
        <label htmlFor="hp-message">Message</label>
        <textarea id="hp-message" name="message" data-trap="clip-path-inset" autoComplete="off" />
      </div>

      {/* 7. transform: scale(0) -- box exists in the layout tree, paints to
             nothing. getBoundingClientRect() reports 0x0 only AFTER the
             transform is applied, so this one doubles as a zero-size check. */}
      <div style={{ transform: "scale(0)", transformOrigin: "top left" }} {...A11Y}>
        <input name="username" data-trap="scale-zero" autoComplete="off" />
      </div>

      {/* 8. height:0 + overflow:hidden. The wrapper is invisible but the input
             inside has a normal computed style of its own -- so a probe that
             only inspects the element and never walks its ANCESTORS is caught. */}
      <div style={{ height: 0, overflow: "hidden" }} {...A11Y}>
        <input name="email_confirm" type="email" data-trap="ancestor-height-zero" autoComplete="off" />
      </div>

      {/* 9. The `hidden` attribute -- trivial, included for completeness. */}
      <div hidden {...A11Y}>
        <input name="website" data-trap="hidden-attr" autoComplete="off" />
      </div>

      {/* 10. Font-size 0 with a transparent colour. Some naive probes measure
              only the box, which here is genuinely non-zero. */}
      <div style={{ fontSize: 0, color: "transparent", lineHeight: 0 }} {...A11Y}>
        <input name="referral_code" style={{ fontSize: 0, height: 2, border: "none" }} data-trap="micro-font" autoComplete="off" />
      </div>

      {/* 11. Crawl traps: links no human can click. A bot that harvests
              a[href] and clicks one at random walks straight into these. */}
      <div style={{ position: "absolute", left: -9999 }} {...A11Y}>
        <a href="/api/collect?trap=offscreen-link" data-trap="offscreen-link" rel="nofollow">
          Pricing details
        </a>
      </div>
      <a
        href="/api/collect?trap=text-indent-link"
        data-trap="text-indent-link"
        rel="nofollow"
        style={{ textIndent: -9999, display: "block", height: 1, overflow: "hidden" }}
        {...A11Y}
      >
        Enterprise plans
      </a>

      {/* 12. Visible to the layout engine, INSIDE an aria-hidden subtree that
              is also visually removed. Tests whether the probe walks ancestors
              for aria-hidden as well as for style. */}
      <div aria-hidden="true" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden", clipPath: "inset(50%)" }}>
        <a href="/api/collect?trap=aria-hidden-link" data-trap="aria-hidden-link" rel="nofollow" tabIndex={-1}>
          Download report
        </a>
      </div>
    </>
  )
}

/**
 * Trap 13, kept separate because it is the only one that is genuinely PAINTED.
 *
 * The input is visible, sized, and unclipped -- but an opaque overlay sits on
 * top of it. A human physically cannot click it: the mouse hits the overlay.
 * Style-based probes all pass this one; only an `elementFromPoint` occlusion
 * test catches it.
 *
 * This is the trap that separates a bot that reasons about *reachability* from
 * one that only reasons about *styling*.
 */
export function OccludedTrap() {
  return (
    <div style={{ position: "relative", height: 44, marginTop: 8 }}>
      <input
        name="postal_code"
        placeholder="Postal code"
        data-trap="occluded-by-overlay"
        autoComplete="off"
        aria-hidden="true"
        tabIndex={-1}
        className="absolute inset-0 w-full rounded-md border border-border bg-secondary px-3 text-sm"
      />
      {/* Opaque, same footprint, higher stacking order. */}
      <div
        className="absolute inset-0 flex items-center rounded-md bg-card px-3 text-sm text-muted-foreground"
        style={{ zIndex: 2 }}
      >
        We only ship to India at the moment.
      </div>
    </div>
  )
}

"""
Honeypot and trap avoidance.

This is the module that most likely decides the round.

An ad-fraud specialist's first instinct is not fingerprinting -- it is bait,
because bait has a *zero false-positive rate*. A field no human can see, that
gets filled anyway, is a bot with certainty. No ML, no scoring, no threshold
tuning. If he has one hour, he will plant traps, and any bot that enumerates
`page.query_selector_all("input")` and fills what it finds is dead on arrival.

Trap varieties to expect:
  - display:none / visibility:hidden / opacity:0 inputs
  - inputs positioned off-screen (left:-9999px, or clipped)
  - zero-size or 1x1 elements
  - fields hidden behind an opaque overlay (visible in DOM, unclickable)
  - text-indent:-9999px links
  - links that are visible but inside an aria-hidden subtree
  - fields whose label is hidden but the input itself is not (subtler)
  - "hidden" via clip-path: inset(100%) or transform: scale(0)
  - elements only reachable by tabbing (tabindex) but visually absent
  - <a rel="nofollow"> crawl traps in a hidden <nav>

Rule: interact ONLY with elements a human eye could actually see and a human
mouse could actually reach. When in doubt, skip it. A bot that completes 70%
of a flow undetected beats a bot that completes 100% and gets flagged.
"""

from __future__ import annotations

# Runs in-page. Returns a verdict per element with the reasons it was rejected,
# so runs are auditable and you can see what the protector planted.
VISIBILITY_PROBE = r"""
(selector) => {
  const results = [];
  const nodes = Array.from(document.querySelectorAll(selector));

  const hiddenAncestor = (el) => {
    let n = el;
    while (n && n !== document.documentElement) {
      if (n.nodeType === 1) {
        const cs = getComputedStyle(n);
        if (cs.display === 'none') return 'ancestor-display-none';
        if (cs.visibility === 'hidden' || cs.visibility === 'collapse')
          return 'ancestor-visibility-hidden';
        if (parseFloat(cs.opacity) < 0.12) return 'ancestor-opacity';
        if (cs.contentVisibility === 'hidden') return 'ancestor-content-visibility';
        if (n.hasAttribute('hidden')) return 'ancestor-hidden-attr';
        if (n.getAttribute('aria-hidden') === 'true') return 'ancestor-aria-hidden';
        const cp = cs.clipPath || cs.webkitClipPath;
        if (cp && /inset\(\s*(100%|50%\s+50%)/.test(cp)) return 'ancestor-clip-path';
        const tf = cs.transform;
        if (tf && /matrix\(0(\.0+)?,\s*0/.test(tf)) return 'ancestor-scale-zero';
      }
      n = n.parentElement;
    }
    return null;
  };

  for (const el of nodes) {
    const reasons = [];
    const cs = getComputedStyle(el);
    const r = el.getBoundingClientRect();

    if (el.type === 'hidden') reasons.push('input-type-hidden');
    if (el.disabled) reasons.push('disabled');
    if (el.readOnly) reasons.push('readonly');
    if (!el.offsetParent && cs.position !== 'fixed' && cs.position !== 'sticky')
      reasons.push('no-offset-parent');

    const anc = hiddenAncestor(el);
    if (anc) reasons.push(anc);

    if (r.width < 3 || r.height < 3) reasons.push('zero-size');
    if (parseFloat(cs.opacity) < 0.12) reasons.push('opacity');
    if (cs.fontSize && parseFloat(cs.fontSize) < 3) reasons.push('micro-font');
    if (parseFloat(cs.textIndent) < -900) reasons.push('text-indent-offscreen');

    // Off-screen in document space, not merely below the fold.
    const absLeft = r.left + window.scrollX;
    const absTop = r.top + window.scrollY;
    if (absLeft + r.width < 0 || absTop + r.height < 0) reasons.push('offscreen-negative');
    if (absLeft > document.documentElement.scrollWidth + 400)
      reasons.push('offscreen-right');
    if (Math.abs(absLeft) > 8000 || Math.abs(absTop) > 40000)
      reasons.push('offscreen-extreme');

    // Occlusion: is this element actually the topmost thing at its centre?
    // Catches fields buried under an opaque overlay -- present in the DOM,
    // unreachable by a real mouse.
    let occluded = false;
    if (r.width >= 3 && r.height >= 3) {
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      if (cx >= 0 && cy >= 0 && cx <= innerWidth && cy <= innerHeight) {
        const top = document.elementFromPoint(cx, cy);
        if (top && top !== el && !el.contains(top) && !top.contains(el)) {
          occluded = true;
          reasons.push('occluded');
        }
      }
    }

    // Suspicious naming. Advisory only -- never the sole reason to skip, since
    // some real forms genuinely use these words.
    const hay = [el.name, el.id, el.className, el.getAttribute('autocomplete')]
      .filter(Boolean).join(' ').toLowerCase();
    const baited = /honey|hpot|h-pot|bot|trap|spam|dummy|decoy|nospam|leave.?blank|do.?not.?fill/
      .test(hay);
    if (baited) reasons.push('suspicious-name');

    results.push({
      tag: el.tagName.toLowerCase(),
      type: el.type || null,
      name: el.name || null,
      id: el.id || null,
      text: (el.innerText || '').slice(0, 60),
      box: { x: r.left + window.scrollX, y: r.top + window.scrollY,
             width: r.width, height: r.height },
      inViewport: r.top >= 0 && r.bottom <= innerHeight,
      occluded,
      reasons,
      safe: reasons.length === 0,
    });
  }
  return results;
}
"""


def partition(probe_results: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split probe output into (safe_to_touch, traps)."""
    safe = [r for r in probe_results if r["safe"]]
    traps = [r for r in probe_results if not r["safe"]]
    return safe, traps


# Fields a human would plausibly fill, mapped to believable values.
def plausible_value(field: dict, rng) -> str | None:
    name = " ".join(filter(None, [
        field.get("name") or "", field.get("id") or "",
        field.get("type") or "",
    ])).lower()

    first = rng.choice(["Aditya", "Rohan", "Meera", "Karthik", "Ananya",
                        "Vikram", "Sneha", "Arjun", "Divya", "Nikhil"])
    last = rng.choice(["Sharma", "Rao", "Nair", "Patel", "Reddy", "Iyer",
                       "Gupta", "Menon", "Desai", "Kulkarni"])

    if "email" in name:
        n = rng.randint(2, 899)
        dom = rng.choice(["gmail.com", "outlook.com", "yahoo.com"])
        return f"{first.lower()}.{last.lower()}{n}@{dom}"
    if "phone" in name or "tel" in name or "mobile" in name:
        return f"9{rng.randint(100000000, 999999999)}"
    if "first" in name:
        return first
    if "last" in name or "surname" in name:
        return last
    if "name" in name:
        return f"{first} {last}"
    if "company" in name or "org" in name:
        return rng.choice(["Northbridge Labs", "Tessellate", "Ardent Systems"])
    if "subject" in name or "title" in name:
        return rng.choice(["Question about pricing", "Demo request",
                           "Need help with my account"])
    if "message" in name or "comment" in name or field["tag"] == "textarea":
        return rng.choice([
            "Hi, I came across your site and wanted to know more about "
            "how the service works. Could someone get back to me?",
            "Is there a student discount available? Thanks in advance.",
            "I had a question about the plans listed on the page.",
        ])
    if "search" in name or "q" == (field.get("name") or ""):
        return rng.choice(["pricing", "contact", "features", "support"])
    if field.get("type") in ("text", None) and "user" in name:
        return f"{first.lower()}{rng.randint(11, 99)}"
    if field.get("type") == "password":
        return None  # never guess at auth flows unless the task requires it
    return None

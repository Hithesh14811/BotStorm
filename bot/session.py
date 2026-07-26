"""
Session orchestration: drive one persona through one human-shaped visit.

Structure of a visit, mirroring how people actually behave:

  1. Arrive with a plausible referrer (a bare deep link with no Referer and no
     prior history is unusual traffic).
  2. Pause before doing anything -- the page has to be *perceived* first.
  3. Read: scroll bursts, reading dwell, cursor drift, hovers that go nowhere.
  4. Maybe interact: click a safe in-page link, or fill a visible form.
  5. Leave without a hard process kill, so unload/visibilitychange fire like
     a real tab closing.

Everything is inside a 12-54s budget to satisfy the competition window with
margin on both ends.
"""

from __future__ import annotations

import asyncio
import json
import math
import random
import time
from pathlib import Path

import config as C
import safety
from humanize import cursor, scroll, timing, typing as ktyping
from persona import Persona


class Session:
    def __init__(self, page, persona: Persona, log_path: Path | None = None):
        self.page = page
        self.p = persona
        self.rng = random.Random(persona.seed + ":behaviour")
        self.x = float(self.rng.randint(120, 600))
        self.y = float(self.rng.randint(120, 420))
        self.events: list[dict] = []
        self.log_path = log_path

    # -- logging -------------------------------------------------------------
    def log(self, kind: str, **kw):
        self.events.append({"t": round(time.time(), 3), "kind": kind, **kw})

    def flush(self):
        if not self.log_path:
            return
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text(json.dumps({
            "seed": self.p.seed,
            "profile": self.p.profile["name"],
            "os": self.p.os,
            "locale": self.p.locale,
            "timezone": self.p.timezone,
            "country": self.p.country,
            "device": self.p.bias.device,
            "events": self.events,
        }, indent=2))

    # -- primitives ----------------------------------------------------------
    async def move_to(self, tx: float, ty: float, target_w: float = 24.0):
        pts = cursor.path_to(self.x, self.y, tx, ty, target_w, self.rng,
                             speed=self.p.bias.speed,
                             precision=self.p.bias.precision)
        for px, py, dt in pts:
            await self.page.mouse.move(px, py)
            await asyncio.sleep(dt)
        self.x, self.y = tx, ty

    async def click_box(self, box: dict):
        tx, ty = cursor.click_point(box, self.rng)
        await self.move_to(tx, ty, target_w=max(box["width"], 8))
        # Settle before pressing -- humans do not click the instant they arrive.
        await asyncio.sleep(self.rng.uniform(0.03, 0.16))
        await self.page.mouse.down()
        await asyncio.sleep(self.rng.uniform(*C.CLICK_DWELL_MS) / 1000.0)
        await self.page.mouse.up()
        self.log("click", x=round(tx, 1), y=round(ty, 1))

    async def type_into(self, box: dict, text: str):
        await self.click_box(box)
        await asyncio.sleep(timing.reaction_delay(self.rng))
        plan = ktyping.keystroke_plan(text, self.rng, speed=self.p.bias.speed)
        kb = self.page.keyboard
        for step in plan:
            await asyncio.sleep(step["pre_delay_s"])
            key = step["key"]
            if key == "\b":
                await kb.down("Backspace")
                await asyncio.sleep(step["dwell_s"])
                await kb.up("Backspace")
            else:
                # down/up with a real dwell, not press(), so keydown->keyup
                # latency is a believable 60-120ms instead of ~0ms.
                await kb.down(key)
                await asyncio.sleep(step["dwell_s"])
                await kb.up(key)
        self.log("typed", chars=len(text), keystrokes=len(plan))

    async def wheel_events(self, events: list[tuple[float, float]]):
        for dy, gap in events:
            await self.page.mouse.wheel(0, dy)
            await asyncio.sleep(gap)

    async def drift(self):
        vw = self.p.profile["viewport"][0]
        vh = self.p.profile["viewport"][1]
        for px, py, dt in cursor.idle_drift(self.x, self.y, self.rng, (vw, vh)):
            await self.page.mouse.move(px, py)
            await asyncio.sleep(dt)
            self.x, self.y = px, py

    # -- probes --------------------------------------------------------------
    async def probe(self, selector: str) -> tuple[list[dict], list[dict]]:
        try:
            results = await self.page.evaluate(safety.VISIBILITY_PROBE, selector)
        except Exception:
            return [], []
        safe, traps = safety.partition(results)
        if traps:
            self.log("traps_avoided",
                     count=len(traps),
                     detail=[{"name": t["name"], "id": t["id"],
                              "reasons": t["reasons"]} for t in traps[:12]])
        return safe, traps

    async def hover_something(self, candidates: list[dict]):
        """Hover an element without clicking it. Humans do this constantly."""
        vis = [c for c in candidates if c["inViewport"] and c["box"]["width"] > 12]
        if not vis:
            return
        c = self.rng.choice(vis)
        b = c["box"]
        sy = await self.page.evaluate("window.scrollY")
        await self.move_to(b["x"] + b["width"] / 2,
                           b["y"] - sy + b["height"] / 2,
                           target_w=b["width"])
        await asyncio.sleep(self.rng.uniform(0.18, 0.95))
        self.log("hover", text=c["text"][:40])

    # -- main flow -----------------------------------------------------------
    async def run(self, url: str, budget_s: float, do_forms: bool = True):
        start = time.time()

        if self.rng.random() < C.WARM_REFERRER_PROB:
            ref = self.rng.choice([
                "https://www.google.com/", "https://www.bing.com/",
                "https://duckduckgo.com/", "https://www.google.co.in/",
            ])
            await self.page.set_extra_http_headers({"Referer": ref})
            self.log("referrer", value=ref)

        await self.page.goto(url, wait_until="domcontentloaded",
                            timeout=30000)
        self.log("navigated", url=url)

        # Perception latency: a human cannot act on a page at t=0ms.
        await asyncio.sleep(timing.reaction_delay(self.rng) +
                            self.rng.uniform(0.25, 0.9))

        try:
            await self.page.wait_for_load_state("networkidle", timeout=6000)
        except Exception:
            pass

        metrics = await self.page.evaluate(
            "() => ({h: document.documentElement.scrollHeight,"
            " vh: window.innerHeight})"
        )

        remaining = budget_s - (time.time() - start)
        read_share = self.rng.uniform(0.52, 0.78) if do_forms else 0.9
        read_budget = max(2.0, remaining * read_share)

        plan = scroll.reading_plan(
            metrics["h"], metrics["vh"], read_budget, self.rng,
            device=self.p.bias.device,
            patience=self.p.bias.patience,
            scrolliness=self.p.bias.scrolliness,
        )

        links, _ = await self.probe("a[href]")

        for step in plan:
            if time.time() - start > budget_s * 0.8:
                break
            if step["type"] == "wheel":
                await self.wheel_events(step["events"])
            elif step["type"] == "read":
                slept = 0.0
                target = step["seconds"]
                # Break the dwell into chunks so drift/hover interleave with it.
                while slept < target:
                    chunk = min(target - slept, self.rng.uniform(0.5, 1.7))
                    await asyncio.sleep(chunk)
                    slept += chunk
                    if self.rng.random() < C.IDLE_DRIFT_PROB * 0.4:
                        await self.drift()
                    if links and self.rng.random() < 0.12:
                        await self.hover_something(links)
            else:
                await asyncio.sleep(step["seconds"])

        # Optional interaction phase.
        if do_forms and time.time() - start < budget_s * 0.82:
            await self.maybe_fill_form(start, budget_s)

        if time.time() - start < budget_s * 0.9 and links:
            await self.hover_something(links)

        elapsed = time.time() - start
        if elapsed < C.SESSION_MIN_S:
            # Never undershoot the competition's 10s floor.
            await asyncio.sleep(C.SESSION_MIN_S - elapsed +
                                self.rng.uniform(0.4, 1.6))

        self.log("session_end", seconds=round(time.time() - start, 2))

    async def maybe_fill_form(self, start: float, budget_s: float):
        fields, _ = await self.probe(
            "input:not([type=hidden]):not([type=submit]):not([type=button]), textarea"
        )
        if not fields:
            return

        fillable = []
        for f in fields:
            val = safety.plausible_value(f, self.rng)
            if val:
                fillable.append((f, val))
        if not fillable:
            return

        # Humans fill top-to-bottom, and rarely fill every field.
        fillable.sort(key=lambda fv: fv[0]["box"]["y"])
        keep = max(1, int(len(fillable) * self.rng.uniform(0.6, 1.0)))
        fillable = fillable[:keep]

        for f, val in fillable:
            if time.time() - start > budget_s * 0.93:
                return
            b = f["box"]
            sy = await self.page.evaluate("window.scrollY")
            vh = self.p.profile["viewport"][1]
            # Scroll the field into view with wheel events, not scrollIntoView.
            if not (0 < b["y"] - sy < vh - 60):
                needed = b["y"] - sy - vh * 0.42
                direction = 1 if needed > 0 else -1
                moved = 0.0
                while moved < abs(needed) and time.time() - start < budget_s * 0.9:
                    burst = scroll.wheel_burst(self.rng, self.p.bias.device,
                                               direction)
                    await self.wheel_events(burst)
                    moved += sum(abs(d) for d, _ in burst)
                sy = await self.page.evaluate("window.scrollY")

            vis_box = dict(b)
            vis_box["y"] = b["y"] - sy
            if vis_box["y"] < 0 or vis_box["y"] > vh - 10:
                continue
            await self.type_into(vis_box, val)
            await asyncio.sleep(self.rng.uniform(0.15, 0.7))

        # Submitting is the highest-risk act; do it only sometimes, and only
        # via a genuinely visible button.
        if self.rng.random() < 0.55 and time.time() - start < budget_s * 0.88:
            buttons, _ = await self.probe(
                "button[type=submit], input[type=submit], button:not([type])"
            )
            vis = [b for b in buttons if b["box"]["width"] > 20]
            if vis:
                b = vis[0]
                sy = await self.page.evaluate("window.scrollY")
                bx = dict(b["box"])
                bx["y"] = b["box"]["y"] - sy
                if 0 < bx["y"] < self.p.profile["viewport"][1] - 10:
                    await asyncio.sleep(timing.reaction_delay(self.rng))
                    await self.click_box(bx)
                    self.log("submitted")
                    await asyncio.sleep(self.rng.uniform(0.8, 2.2))

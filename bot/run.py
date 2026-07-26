"""
Fleet launcher.

    python run.py --target https://his-site.example --bots 8 \
        --proxy-file proxies.txt --concurrency 3

Design notes that matter for the round:

  * One browser instance per bot, torn down cleanly. Reusing a context across
    bots leaks storage state and correlates sessions.
  * Poisson arrivals, not fixed spacing.
  * Each bot gets its own persona AND its own behavioural bias, so the fleet
    does not share one behavioural distribution.
  * geoip=True lets Camoufox align timezone/locale/geolocation to the proxy
    exit IP inside the browser, which is the single highest-value consistency
    guarantee available.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from pathlib import Path

import config as C
import persona as P
from humanize import timing
from session import Session


def parse_proxy(raw: str) -> dict | None:
    """Accepts host:port, host:port:user:pass, or scheme://user:pass@host:port."""
    raw = raw.strip()
    if not raw or raw.startswith("#"):
        return None
    if "://" in raw:
        return {"server": raw}
    parts = raw.split(":")
    if len(parts) == 2:
        return {"server": f"http://{parts[0]}:{parts[1]}"}
    if len(parts) == 4:
        host, port, user, pwd = parts
        return {"server": f"http://{host}:{port}",
                "username": user, "password": pwd}
    return {"server": raw if "://" in raw else f"http://{raw}"}


def proxy_to_url(proxy: dict | None) -> str | None:
    if not proxy:
        return None
    server = proxy["server"]
    if "username" in proxy:
        scheme, rest = server.split("://", 1)
        return f"{scheme}://{proxy['username']}:{proxy['password']}@{rest}"
    return server


async def run_one(idx: int, url: str, proxy: dict | None, headless: bool,
                  log_dir: Path, do_forms: bool) -> dict:
    from camoufox.async_api import AsyncCamoufox

    seed = f"{uuid.uuid4()}"
    rng = random.Random(seed)

    per = P.build_persona(seed, proxy_to_url(proxy))
    budget = timing.session_budget(rng, per.bias.patience)

    print(f"[bot {idx:02d}] persona={per.profile['name']} os={per.os} "
          f"geo={per.country} tz={per.timezone} langs={','.join(per.locales)} "
          f"dev={per.bias.device} budget={budget:.1f}s", flush=True)

    # Camoufox's `window=` is the OUTER window size, not the viewport --
    # generate_fingerprint() routes it straight into handle_window_size(), which
    # assigns outerWidth/outerHeight. Handing it the viewport shrinks the real
    # OS window by one chrome height, so the true layout viewport ends up
    # shorter than the innerHeight we advertise.
    ow, oh = P.outer_size(per.profile)
    result = {"idx": idx, "seed": seed, "ok": False}

    try:
        async with AsyncCamoufox(
            headless=headless,
            proxy=proxy,
            geoip=True,           # align tz/locale/geo to the exit IP
            humanize=False,       # we supply our own, richer humanisation
            # A LIST, not a string: Camoufox only populates `locale:all`
            # (navigator.languages + Accept-Language) for 2+ locales.
            locale=per.locales,
            os=[per.os],
            config=P.camoufox_config(per),
            window=(ow, oh),
            block_webrtc=True,    # prevent the real LAN IP leaking via WebRTC
            i_know_what_im_doing=True,
        ) as browser:
            page = await browser.new_page()
            sess = Session(page, per, log_dir / f"bot-{idx:02d}-{seed[:8]}.json")
            await sess.run(url, budget, do_forms=do_forms)
            sess.flush()
            result["ok"] = True
            result["events"] = len(sess.events)
            traps = sum(e.get("count", 0) for e in sess.events
                        if e["kind"] == "traps_avoided")
            result["traps_avoided"] = traps
            print(f"[bot {idx:02d}] done  events={len(sess.events)} "
                  f"traps_avoided={traps}", flush=True)
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        print(f"[bot {idx:02d}] FAILED {result['error']}", flush=True)

    return result


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--bots", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=1)
    ap.add_argument("--proxy-file")
    ap.add_argument("--proxy", action="append", default=[])
    ap.add_argument("--headless", action="store_true",
                    help="Prefer headful (omit this) under Xvfb; headless is "
                         "detectable in ways no spoof fully covers.")
    ap.add_argument("--no-forms", action="store_true")
    ap.add_argument("--log-dir", default="runs")
    args = ap.parse_args()

    proxies: list[dict] = []
    for raw in args.proxy:
        pr = parse_proxy(raw)
        if pr:
            proxies.append(pr)
    if args.proxy_file:
        for line in Path(args.proxy_file).read_text().splitlines():
            pr = parse_proxy(line)
            if pr:
                proxies.append(pr)

    if not proxies:
        print("! no proxies supplied -- all bots will share your real IP, "
              "which collapses them into one obvious cluster.", file=sys.stderr)
        proxies = [None]

    rng = random.Random()
    arrivals = timing.poisson_arrivals(args.bots, C.FLEET_ARRIVAL_MEAN_S, rng)
    log_dir = Path(args.log_dir)
    sem = asyncio.Semaphore(max(1, args.concurrency))

    async def scheduled(idx: int, at: float):
        await asyncio.sleep(at)
        async with sem:
            return await run_one(
                idx, args.target,
                proxies[idx % len(proxies)],
                args.headless, log_dir, not args.no_forms,
            )

    results = await asyncio.gather(*[
        scheduled(i + 1, t) for i, t in enumerate(arrivals)
    ])

    ok = sum(1 for r in results if r["ok"])
    traps = sum(r.get("traps_avoided", 0) for r in results)
    print(f"\n=== {ok}/{len(results)} sessions completed, "
          f"{traps} traps avoided. Logs in {log_dir}/ ===")


if __name__ == "__main__":
    asyncio.run(main())

import { NextResponse } from "next/server"
import { clear, list } from "@/lib/store"

/** Never cache: the whole point is watching verdicts land in real time. */
export const dynamic = "force-dynamic"

export async function GET() {
  // The raw `ev` arrays hold up to 4000 samples per channel. They are what the
  // scorer chews on, but shipping them to the dashboard would make the poll
  // response megabytes wide, so we summarise instead and keep the pieces a
  // human actually reads.
  const rows = list().map((r) => ({
    id: r.id,
    sid: r.sid,
    at: r.at,
    reason: r.reason,
    score: r.score,
    duration: r.duration,
    ip: r.ip,
    ua: r.ua,
    headerFlags: r.headerFlags,
    counts: r.counts,
    signals: r.signals,
    traps: r.report?.traps ?? [],
    env: {
      screen: r.report?.env?.screen,
      viewport: r.report?.env?.viewport,
      outer: r.report?.env?.outer,
      dpr: r.report?.env?.dpr,
      cores: r.report?.env?.cores,
      langs: r.report?.env?.langs,
      fonts: r.report?.env?.fonts,
      webgl: r.report?.env?.webgl,
      canvas: r.report?.env?.canvas,
    },
    tells: {
      ua: r.report?.tells?.ua,
      platform: r.report?.tells?.platform,
      tz: r.report?.tells?.tz,
      tzOffset: r.report?.tells?.tzOffset,
      webdriver: r.report?.tells?.webdriver,
      patched: r.report?.tells?.patched,
      injectedGlobals: r.report?.tells?.injectedGlobals,
      ownNavProps: r.report?.tells?.ownNavProps,
    },
  }))

  return NextResponse.json({ rows, at: Date.now() })
}

export async function DELETE() {
  clear()
  return NextResponse.json({ ok: true })
}

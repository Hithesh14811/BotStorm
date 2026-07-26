import { type NextRequest, NextResponse } from "next/server"
import { scoreSession, type Report } from "@/lib/score"
import { put } from "@/lib/store"

/**
 * Server-side header analysis. Client JS can lie about anything; the request
 * headers and TLS layer are a second, harder-to-forge opinion. Disagreement
 * between the two is itself the signal.
 */
function headerFlags(req: NextRequest, report: Report): string[] {
  const f: string[] = []
  const h = req.headers
  const ua = h.get("user-agent") || ""

  if (!ua) f.push("missing User-Agent")
  if (/python-requests|curl|wget|Go-http-client|axios|node-fetch|okhttp|Scrapy|libwww|HeadlessChrome|Puppeteer|Playwright/i.test(ua))
    f.push("automation signature in User-Agent")

  if (!h.get("accept-language")) f.push("missing Accept-Language")
  if (!h.get("accept-encoding")) f.push("missing Accept-Encoding")
  if (!h.get("accept")) f.push("missing Accept")

  // Chromium sends client hints; a UA claiming Chrome without them is odd.
  const isChromeUA = /Chrome\/\d+/.test(ua) && !/Firefox/.test(ua)
  if (isChromeUA && !h.get("sec-ch-ua")) f.push("Chrome UA without Sec-CH-UA hints")

  // Client hints must agree with the UA string.
  const chUA = h.get("sec-ch-ua") || ""
  const uaVer = ua.match(/Chrome\/(\d+)/)?.[1]
  const chVer = chUA.match(/"Chromium";v="(\d+)"|"Google Chrome";v="(\d+)"/)
  const chNum = chVer?.[1] || chVer?.[2]
  if (uaVer && chNum && uaVer !== chNum) f.push(`UA Chrome ${uaVer} vs hint ${chNum}`)

  const chMobile = h.get("sec-ch-ua-mobile")
  if (chMobile) {
    const hintMobile = chMobile === "?1"
    const uaMobile = /Mobi|Android|iPhone/.test(ua)
    if (hintMobile !== uaMobile) f.push("Sec-CH-UA-Mobile contradicts UA")
  }

  const chPlat = (h.get("sec-ch-ua-platform") || "").replace(/"/g, "")
  if (chPlat) {
    const claims =
      (/Windows/.test(ua) && chPlat !== "Windows") ||
      (/Mac OS X/.test(ua) && chPlat !== "macOS") ||
      (/Android/.test(ua) && chPlat !== "Android")
    if (claims) f.push(`Sec-CH-UA-Platform "${chPlat}" contradicts UA`)
  }

  // Fetch metadata should be present on modern browser requests.
  if (isChromeUA && !h.get("sec-fetch-site")) f.push("missing Sec-Fetch-* metadata")

  // Language vs the timezone the client reported.
  const al = (h.get("accept-language") || "").toLowerCase()
  const tz = String(report?.tells?.tz || "")
  if (al && tz) {
    const pairs: Array<[RegExp, RegExp]> = [
      [/^en-us/, /America\//],
      [/^en-gb/, /Europe\/London/],
      [/^de/, /Europe\/(Berlin|Vienna|Zurich)/],
      [/^ja/, /Asia\/Tokyo/],
      [/^hi|^en-in/, /Asia\/(Kolkata|Calcutta)/],
    ]
    for (const [lang, zone] of pairs) {
      if (lang.test(al) && tz && !zone.test(tz)) {
        f.push(`Accept-Language "${al.split(",")[0]}" vs timezone "${tz}"`)
        break
      }
    }
  }

  // The client's self-reported UA should match the transport UA.
  const clientUA = String(report?.tells?.ua || "")
  if (clientUA && ua && clientUA !== ua) f.push("navigator.userAgent differs from header")

  return f
}

export async function POST(req: NextRequest) {
  let body: { reason?: string; report?: Report }
  try {
    body = await req.json()
  } catch {
    return NextResponse.json({ ok: false, error: "bad json" }, { status: 400 })
  }

  const report = body.report
  if (!report?.sid) return NextResponse.json({ ok: false, error: "no report" }, { status: 400 })

  const { score, signals } = scoreSession(report)
  const flags = headerFlags(req, report)

  // Header disagreements are weighted heavily — they are hard to fake from
  // inside the page and cheap for a defender to check.
  const headerPenalty = flags.length * 18
  const combined = Math.round(100 * (1 - Math.exp(-(-55 * Math.log(1 - score / 100) + headerPenalty) / 55)))

  const all = [
    ...signals,
    ...flags.map((d) => ({
      id: "header",
      label: "Header/transport inconsistency",
      weight: 18,
      detail: d,
      severity: "fatal" as const,
    })),
  ].sort((a, b) => b.weight - a.weight)

  put({
    id: `${report.sid}-${Date.now()}`,
    sid: report.sid,
    at: Date.now(),
    reason: body.reason || "?",
    score: Math.min(100, Number.isFinite(combined) ? combined : score),
    signals: all,
    duration: report.duration,
    ip:
      req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ||
      req.headers.get("x-real-ip") ||
      "local",
    ua: req.headers.get("user-agent") || "",
    headerFlags: flags,
    counts: report.counts || {},
    report,
  })

  return NextResponse.json({ ok: true, score, flags: flags.length })
}

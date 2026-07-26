"use client"

import { useState } from "react"
import useSWR from "swr"
import type { Signal } from "@/lib/score"
import { verdict } from "@/lib/score"

type Row = {
  id: string
  sid: string
  at: number
  reason: string
  score: number
  duration: number
  ip: string
  ua: string
  headerFlags: string[]
  counts: Record<string, number>
  signals: Signal[]
  traps: Array<{ trap: string; type: string; t: number }>
  env: Record<string, unknown>
  tells: Record<string, unknown>
}

const fetcher = (url: string) => fetch(url).then((r) => r.json())

const SEVERITY_CLASS: Record<Signal["severity"], string> = {
  fatal: "text-destructive",
  warn: "text-foreground",
  info: "text-muted-foreground",
}

function scoreTone(score: number) {
  if (score >= 40) return "text-destructive"
  if (score >= 25) return "text-foreground"
  return "text-primary"
}

function Stat({ label, value, tone = "" }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card px-4 py-3">
      <span className="text-xs uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className={`font-mono text-2xl leading-none ${tone}`}>{value}</span>
    </div>
  )
}

export function VerdictFeed() {
  const { data, mutate, isLoading } = useSWR<{ rows: Row[] }>("/api/report", fetcher, {
    refreshInterval: 2000,
  })
  const [open, setOpen] = useState<string | null>(null)

  const rows = data?.rows ?? []
  const scores = rows.map((r) => r.score)
  const meanScore = scores.length ? Math.round(scores.reduce((s, x) => s + x, 0) / scores.length) : 0
  const worst = scores.length ? Math.max(...scores) : 0
  const clean = rows.filter((r) => r.score < 10).length

  return (
    <div className="flex flex-col gap-8">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Sessions" value={String(rows.length)} />
        <Stat label="Mean score" value={String(meanScore)} tone={scoreTone(meanScore)} />
        <Stat label="Worst" value={String(worst)} tone={scoreTone(worst)} />
        <Stat label="Passed clean" value={`${clean}/${rows.length || 0}`} tone={clean === rows.length && rows.length > 0 ? "text-primary" : ""} />
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => mutate()}
          className="h-9 rounded-md border border-border px-4 text-sm transition-colors hover:bg-accent"
        >
          Refresh
        </button>
        <button
          onClick={async () => {
            await fetch("/api/report", { method: "DELETE" })
            mutate()
          }}
          className="h-9 rounded-md border border-border px-4 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
        >
          Clear range
        </button>
        <span className="ml-auto font-mono text-xs text-muted-foreground">polling every 2s</span>
      </div>

      {isLoading && rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : rows.length === 0 ? (
        <div className="flex flex-col gap-3 rounded-lg border border-border bg-card px-5 py-6">
          <p className="text-sm font-medium">No sessions recorded yet.</p>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Point the fleet at the range and reports will appear here as they land:
          </p>
          <pre className="overflow-x-auto rounded-md bg-secondary px-4 py-3 font-mono text-xs leading-relaxed">
            {"cd bot\npython run.py --target http://localhost:3000 --bots 5 --concurrency 2"}
          </pre>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Open the range yourself first and interact normally — that gives you the human baseline to beat.
          </p>
        </div>
      ) : (
        <ul className="flex flex-col gap-3">
          {rows.map((r) => {
            const v = verdict(r.score)
            const isOpen = open === r.id
            return (
              <li key={r.id} className="rounded-lg border border-border bg-card">
                <button
                  onClick={() => setOpen(isOpen ? null : r.id)}
                  className="flex w-full flex-wrap items-center gap-4 px-5 py-4 text-left"
                  aria-expanded={isOpen}
                >
                  <span className={`font-mono text-3xl leading-none ${scoreTone(r.score)}`}>
                    {String(r.score).padStart(2, "0")}
                  </span>
                  <span className="flex flex-col gap-1">
                    <span className={`text-sm font-medium ${v.tone === "ok" ? "text-primary" : v.tone === "warn" ? "text-foreground" : "text-destructive"}`}>
                      {v.label}
                    </span>
                    <span className="font-mono text-xs text-muted-foreground">
                      {r.sid.slice(0, 8)} · {(r.duration / 1000).toFixed(1)}s · {r.reason} · {r.ip}
                    </span>
                  </span>
                  <span className="ml-auto flex flex-wrap items-center gap-3 font-mono text-xs text-muted-foreground">
                    <span>{r.counts.move ?? 0} move</span>
                    <span>{r.counts.key ?? 0} key</span>
                    <span>{r.counts.wheel ?? 0} wheel</span>
                    <span>{r.counts.click ?? 0} click</span>
                    <span aria-hidden="true">{isOpen ? "−" : "+"}</span>
                  </span>
                </button>

                {isOpen && (
                  <div className="flex flex-col gap-5 border-t border-border px-5 py-4">
                    {r.traps.length > 0 && (
                      <div className="flex flex-col gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3">
                        <span className="text-sm font-semibold text-destructive">
                          Honeypots touched — instant fail
                        </span>
                        <ul className="flex flex-col gap-1 font-mono text-xs text-foreground">
                          {r.traps.map((t, i) => (
                            <li key={`${t.trap}-${i}`}>
                              {t.trap} · {t.type} · {(t.t / 1000).toFixed(2)}s
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    <div className="flex flex-col gap-2">
                      <h3 className="text-xs uppercase tracking-wider text-muted-foreground">
                        Signals ({r.signals.length})
                      </h3>
                      {r.signals.length === 0 ? (
                        <p className="text-sm text-primary">Nothing fired. Indistinguishable from human on these checks.</p>
                      ) : (
                        <ul className="flex flex-col gap-3">
                          {r.signals.map((s, i) => (
                            <li key={`${s.id}-${i}`} className="flex gap-3">
                              <span className="w-8 shrink-0 font-mono text-sm text-muted-foreground">+{s.weight}</span>
                              <span className="flex flex-col gap-1">
                                <span className={`text-sm font-medium ${SEVERITY_CLASS[s.severity]}`}>{s.label}</span>
                                <span className="text-sm leading-relaxed text-muted-foreground">{s.detail}</span>
                              </span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="flex flex-col gap-2">
                        <h3 className="text-xs uppercase tracking-wider text-muted-foreground">Environment</h3>
                        <pre className="overflow-x-auto rounded-md bg-secondary px-3 py-2 font-mono text-xs leading-relaxed">
                          {JSON.stringify(r.env, null, 1)}
                        </pre>
                      </div>
                      <div className="flex flex-col gap-2">
                        <h3 className="text-xs uppercase tracking-wider text-muted-foreground">Tells</h3>
                        <pre className="overflow-x-auto rounded-md bg-secondary px-3 py-2 font-mono text-xs leading-relaxed">
                          {JSON.stringify(r.tells, null, 1)}
                        </pre>
                      </div>
                    </div>

                    <div className="flex flex-col gap-2">
                      <h3 className="text-xs uppercase tracking-wider text-muted-foreground">User-Agent</h3>
                      <p className="break-all font-mono text-xs text-muted-foreground">{r.ua || "—"}</p>
                    </div>
                  </div>
                )}
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

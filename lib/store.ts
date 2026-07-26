/**
 * In-memory session store for the harness. Deliberately not a database —
 * this is a practice range, and you want it wiped on restart.
 */
import type { Report, Signal } from "./score"

export type Verdicted = {
  id: string
  sid: string
  at: number
  reason: string
  score: number
  signals: Signal[]
  duration: number
  ip: string
  ua: string
  headerFlags: string[]
  counts: Record<string, number>
  report: Report
}

type Store = { rows: Verdicted[] }

const g = globalThis as unknown as { __harness?: Store }
if (!g.__harness) g.__harness = { rows: [] }
const store = g.__harness

export function put(row: Verdicted) {
  // Collapse repeat reports from the same session id, keeping the richest.
  const i = store.rows.findIndex((r) => r.sid === row.sid)
  if (i >= 0 && store.rows[i].duration <= row.duration) store.rows[i] = row
  else if (i < 0) store.rows.unshift(row)
  store.rows = store.rows.slice(0, 200)
}

export function list() {
  return store.rows
}

export function clear() {
  store.rows = []
}

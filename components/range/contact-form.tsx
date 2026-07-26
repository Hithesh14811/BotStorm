"use client"

import { useState } from "react"
import { Honeypots, OccludedTrap } from "./honeypots"

/**
 * The interaction target.
 *
 * Legitimate fields are interleaved with the honeypot battery, exactly as a
 * defender would plant them -- traps before, between, and after the real
 * inputs, so a bot cannot pass by simply "taking the first N visible fields".
 *
 * Submission is intercepted so a successful run does not navigate away. That
 * matters for measurement: a real navigation tears down probe.js mid-session
 * and you lose the richest part of the report.
 */
export function ContactForm() {
  const [sent, setSent] = useState(false)

  return (
    <section id="contact" className="flex flex-col gap-6">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-semibold tracking-tight text-balance">Talk to the team</h2>
        <p className="text-sm leading-relaxed text-muted-foreground">
          Tell us roughly what you are measuring and we will point you at the right plan.
        </p>
      </div>

      {sent ? (
        <p role="status" className="rounded-md border border-primary/30 bg-primary/10 px-4 py-3 text-sm text-foreground">
          Thanks — we&apos;ll be in touch shortly.
        </p>
      ) : (
        <form
          className="flex max-w-xl flex-col gap-4"
          onSubmit={(e) => {
            e.preventDefault()
            setSent(true)
          }}
        >
          {/* Traps planted BEFORE the real fields. */}
          <Honeypots />

          <div className="flex flex-col gap-2">
            <label htmlFor="c-name" className="text-sm font-medium">
              Your name
            </label>
            <input
              id="c-name"
              name="name"
              required
              autoComplete="name"
              className="h-10 rounded-md border border-border bg-secondary px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="flex flex-col gap-2">
            <label htmlFor="c-workmail" className="text-sm font-medium">
              Work email
            </label>
            <input
              id="c-workmail"
              name="work_email"
              type="email"
              required
              autoComplete="email"
              className="h-10 rounded-md border border-border bg-secondary px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          {/* The occlusion trap sits mid-form, where it looks like a real row. */}
          <OccludedTrap />

          <div className="flex flex-col gap-2">
            <label htmlFor="c-note" className="text-sm font-medium">
              What are you working on?
            </label>
            <textarea
              id="c-note"
              name="note"
              rows={4}
              className="rounded-md border border-border bg-secondary px-3 py-2 text-sm leading-relaxed outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <button
            type="submit"
            className="h-10 self-start rounded-md bg-primary px-5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
          >
            Send message
          </button>
        </form>
      )}
    </section>
  )
}

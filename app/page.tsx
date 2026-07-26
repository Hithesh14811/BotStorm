import Script from "next/script"
import Link from "next/link"
import { ContactForm } from "@/components/range/contact-form"

/**
 * The practice range.
 *
 * A deliberately ordinary-looking marketing page: enough copy to make a
 * reading pass meaningful, enough links to hover, and a form worth filling.
 * public/probe.js instruments it and POSTs a full behavioural report to
 * /api/collect, which scores it with lib/score.ts.
 *
 * Point the bot here, then read /dashboard to see precisely which signal
 * betrayed it.
 */

const FEATURES = [
  {
    title: "Event capture",
    body: "Every pointer sample, keystroke pair, and wheel notch is recorded with a high-resolution timestamp, so you can reconstruct a session exactly as it happened rather than guessing from aggregates.",
  },
  {
    title: "Kinematic scoring",
    body: "Movement is checked for a ballistic velocity profile, path efficiency, step-size entropy, and lag-1 autocorrelation. Straight lines and metronomic sampling stand out immediately.",
  },
  {
    title: "Keystroke biometrics",
    body: "Digraph latency varies by which hand and which finger types each pair of characters. Flat inter-key timing is the single most common tell in scripted form fills.",
  },
  {
    title: "Transport cross-check",
    body: "Request headers and TLS characteristics form a second opinion that page JavaScript cannot influence. Disagreement between the two layers is the signal, not either layer alone.",
  },
]

const FAQ = [
  {
    q: "How long is a measured session?",
    a: "Reports are flushed at fifteen and forty-five seconds, and again on page hide, so both short bounces and long reads are captured without relying on an unload event that may never fire.",
  },
  {
    q: "What counts as a hard failure?",
    a: "Anything with a zero false-positive rate: a self-identifying driver flag, an untrusted synthetic event, or an interaction with an element that was never painted on screen.",
  },
  {
    q: "Are weak signals combined?",
    a: "Yes. Individual weights are summed and passed through a saturating exponential, so a pile of small oddities can build confidence without any single medium-strength signal maxing the score by itself.",
  },
]

export default function RangePage() {
  return (
    <>
      <Script src="/probe.js" strategy="afterInteractive" />

      <div className="flex min-h-screen flex-col">
        <header className="sticky top-0 z-10 border-b border-border bg-background/85 backdrop-blur">
          <nav className="mx-auto flex w-full max-w-3xl items-center gap-6 px-6 py-4">
            <span className="font-mono text-sm font-semibold tracking-tight">northwind/analytics</span>
            <div className="ml-auto flex items-center gap-5 text-sm text-muted-foreground">
              <a href="#features" className="transition-colors hover:text-foreground">
                Features
              </a>
              <a href="#pricing" className="transition-colors hover:text-foreground">
                Pricing
              </a>
              <a href="#faq" className="transition-colors hover:text-foreground">
                FAQ
              </a>
              <a href="#contact" className="transition-colors hover:text-foreground">
                Contact
              </a>
            </div>
          </nav>
        </header>

        <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-16 px-6 py-14">
          <section className="flex flex-col gap-4">
            <p className="font-mono text-xs uppercase tracking-widest text-primary">Session analytics</p>
            <h1 className="text-4xl font-semibold leading-tight tracking-tight text-balance">
              Understand what actually happened on the page
            </h1>
            <p className="max-w-2xl text-base leading-relaxed text-muted-foreground text-pretty">
              Northwind records the raw interaction stream behind every visit — pointer trajectories, keystroke
              timing, scroll physics — and turns it into something you can reason about. No sampling, no
              guesswork, no dashboards full of numbers nobody can act on.
            </p>
            <div className="flex flex-wrap items-center gap-3 pt-2">
              <a
                href="#contact"
                className="h-10 rounded-md bg-primary px-5 text-sm font-medium leading-10 text-primary-foreground transition-opacity hover:opacity-90"
              >
                Request access
              </a>
              <a
                href="#features"
                className="h-10 rounded-md border border-border px-5 text-sm font-medium leading-10 transition-colors hover:bg-accent"
              >
                See how it works
              </a>
            </div>
          </section>

          <section id="features" className="flex flex-col gap-6">
            <h2 className="text-2xl font-semibold tracking-tight">What gets measured</h2>
            <div className="grid gap-4 md:grid-cols-2">
              {FEATURES.map((f) => (
                <article key={f.title} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-5">
                  <h3 className="text-sm font-semibold">{f.title}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{f.body}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="pricing" className="flex flex-col gap-6">
            <h2 className="text-2xl font-semibold tracking-tight">Pricing</h2>
            <div className="grid gap-4 md:grid-cols-3">
              {[
                { name: "Solo", price: "₹0", note: "10k sessions / month, 7-day retention." },
                { name: "Team", price: "₹2,400", note: "500k sessions / month, 90-day retention." },
                { name: "Scale", price: "Talk to us", note: "Unmetered, self-hosted collector, SSO." },
              ].map((p) => (
                <article key={p.name} className="flex flex-col gap-2 rounded-lg border border-border bg-card p-5">
                  <h3 className="text-sm font-semibold">{p.name}</h3>
                  <p className="font-mono text-2xl">{p.price}</p>
                  <p className="text-sm leading-relaxed text-muted-foreground">{p.note}</p>
                </article>
              ))}
            </div>
          </section>

          <section id="faq" className="flex flex-col gap-6">
            <h2 className="text-2xl font-semibold tracking-tight">Questions</h2>
            <div className="flex flex-col gap-5">
              {FAQ.map((item) => (
                <div key={item.q} className="flex flex-col gap-2 border-l-2 border-border pl-4">
                  <h3 className="text-sm font-semibold">{item.q}</h3>
                  <p className="text-sm leading-relaxed text-muted-foreground">{item.a}</p>
                </div>
              ))}
            </div>
          </section>

          <ContactForm />
        </main>

        <footer className="border-t border-border">
          <div className="mx-auto flex w-full max-w-3xl flex-wrap items-center gap-4 px-6 py-6 text-sm text-muted-foreground">
            <span className="font-mono text-xs">northwind/analytics — practice range</span>
            <Link href="/dashboard" className="ml-auto font-mono text-xs text-primary hover:underline">
              open verdict dashboard →
            </Link>
          </div>
        </footer>
      </div>
    </>
  )
}

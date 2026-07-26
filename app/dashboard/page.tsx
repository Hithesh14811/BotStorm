import Link from "next/link"
import { VerdictFeed } from "@/components/dashboard/verdict-feed"

export const metadata = {
  title: "Verdicts — Detection Range",
  description: "Live automation scores for every session recorded on the practice range.",
}

export default function DashboardPage() {
  return (
    <div className="mx-auto flex min-h-screen w-full max-w-5xl flex-col gap-8 px-6 py-10">
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-4">
          <h1 className="text-2xl font-semibold tracking-tight">Verdicts</h1>
          <Link href="/" className="ml-auto font-mono text-xs text-primary hover:underline">
            ← back to range
          </Link>
        </div>
        <p className="max-w-2xl text-sm leading-relaxed text-muted-foreground text-pretty">
          Every session that loads the range reports here. Score runs 0 (indistinguishable from human) to 100
          (certainly automated). Expand a row to see exactly which check fired and why — that detail is the
          thing worth reading, because it tells you what to fix in the bot.
        </p>
      </header>

      <VerdictFeed />
    </div>
  )
}

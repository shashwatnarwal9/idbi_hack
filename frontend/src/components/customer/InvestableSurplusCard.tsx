import { PiggyBank } from "lucide-react";

import { inr } from "../../lib/format";
import type { SurplusLine } from "../../mocks/types";
import { Card } from "../Card";

interface InvestableSurplusCardProps {
  lines: SurplusLine[];
  surplus: number;
  savingsTitle?: string;
  savingsNote: string;
}

export function InvestableSurplusCard({
  lines,
  surplus,
  savingsTitle = "Saving potential",
  savingsNote,
}: InvestableSurplusCardProps) {
  const maxAbs = Math.max(...lines.map((line) => Math.abs(line.amount)), 1);

  return (
    <Card
      title="Investable Surplus"
      subtitle="What is safely deployable each month"
    >
      <div className="space-y-3">
        {lines.map((line) => {
          const positive = line.amount >= 0;
          return (
            <div key={line.label} className="flex items-center gap-3">
              <span className="w-32 shrink-0 text-sm text-ink-soft">
                {line.label}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-sage">
                <div
                  className={`h-full rounded-full ${positive ? "bg-emerald" : "bg-negative/80"}`}
                  style={{ width: `${(Math.abs(line.amount) / maxAbs) * 100}%` }}
                />
              </div>
              <span
                className={`w-24 shrink-0 text-right text-sm font-semibold ${
                  positive ? "text-emerald" : "text-negative"
                }`}
              >
                {positive ? "+" : "−"}
                {inr(Math.abs(line.amount))}
              </span>
            </div>
          );
        })}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-line pt-4">
        <span className="text-sm font-semibold uppercase tracking-wide">
          Surplus
        </span>
        <span className="text-lg font-bold text-emerald">{inr(surplus)}/mo</span>
      </div>

      <div className="mt-4 flex items-start gap-3 rounded-xl bg-mint p-4">
        <div className="rounded-lg bg-white/60 p-2 text-forest">
          <PiggyBank size={18} strokeWidth={1.8} />
        </div>
        <div>
          <div className="text-sm font-semibold text-forest-deep">
            {savingsTitle}
          </div>
          <p className="mt-0.5 text-xs leading-relaxed text-forest">
            {savingsNote}
          </p>
        </div>
      </div>
    </Card>
  );
}

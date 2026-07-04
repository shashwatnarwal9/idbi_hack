import { inr } from "../../lib/format";
import type { IncomeStream } from "../../mocks/types";
import { Card } from "../Card";
import { ProgressBar } from "../ProgressBar";

interface IncomeReconstructionCardProps {
  declaredMonthly: number | null;
  reconstructedMonthly: number;
  streams: IncomeStream[];
}

export function IncomeReconstructionCard({
  declaredMonthly,
  reconstructedMonthly,
  streams,
}: IncomeReconstructionCardProps) {
  const upliftPct =
    declaredMonthly && declaredMonthly > 0
      ? Math.round(((reconstructedMonthly - declaredMonthly) / declaredMonthly) * 100)
      : null;

  return (
    <Card
      title="Income Reconstruction"
      subtitle="Derived from transaction narrations, not self-reporting"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl bg-sage p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            Declared monthly
          </div>
          <div className="mt-1 text-xl font-semibold text-ink-soft">
            {declaredMonthly !== null ? inr(declaredMonthly) : "unavailable"}
          </div>
          <div className="mt-0.5 text-xs text-ink-muted">
            self-reported at onboarding
          </div>
        </div>
        <div className="rounded-xl bg-mint p-4">
          <div className="text-xs font-medium uppercase tracking-wide text-forest">
            Reconstructed avg
          </div>
          <div className="mt-1 text-xl font-semibold text-forest-deep">
            {inr(reconstructedMonthly)}
          </div>
          <div className="mt-0.5 text-xs font-medium text-emerald">
            {upliftPct !== null ? `+${upliftPct}% vs declared` : "no declared income"}
          </div>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        {streams.map((stream) => (
          <div key={stream.label}>
            <div className="flex items-baseline justify-between">
              <span className="text-sm font-medium">{stream.label}</span>
              <span className="text-sm font-semibold">{stream.sharePct}%</span>
            </div>
            <div className="mt-1.5">
              <ProgressBar value={stream.sharePct / 100} tone="brand" />
            </div>
            <p className="mt-1.5 text-xs text-ink-muted">Pattern: {stream.note}</p>
          </div>
        ))}
      </div>
    </Card>
  );
}

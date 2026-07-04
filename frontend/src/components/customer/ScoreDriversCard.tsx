import { CheckCheck, Download, RotateCcw } from "lucide-react";

import type { ScoreDriver } from "../../mocks/types";
import { Card } from "../Card";

interface DriverRowProps {
  driver: ScoreDriver;
  maxAbs: number;
}

function DriverRow({ driver, maxAbs }: DriverRowProps) {
  const positive = driver.points >= 0;
  return (
    <div className="flex items-center gap-3">
      <span className="w-44 shrink-0 truncate font-mono text-xs text-ink-soft">
        {driver.label}
      </span>
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-sage">
        <div
          className={`h-full rounded-full ${positive ? "bg-emerald" : "bg-negative/80"}`}
          style={{ width: `${(Math.abs(driver.points) / maxAbs) * 100}%` }}
        />
      </div>
      <span
        className={`w-14 shrink-0 text-right text-sm font-semibold ${
          positive ? "text-emerald" : "text-negative"
        }`}
      >
        {positive ? "+" : "−"}
        {Math.abs(driver.points).toFixed(2)}
      </span>
    </div>
  );
}

interface ScoreDriversCardProps {
  positive: ScoreDriver[];
  negative: ScoreDriver[];
  reasoning: string;
  reviewed: boolean;
  busy?: boolean;
  onExport?: () => void;
  onToggleReviewed?: () => void;
}

/** SHAP drivers split by sign, the review action and the audit export. */
export function ScoreDriversCard({
  positive,
  negative,
  reasoning,
  reviewed,
  busy = false,
  onExport,
  onToggleReviewed,
}: ScoreDriversCardProps) {
  const maxAbs = Math.max(
    ...[...positive, ...negative].map((d) => Math.abs(d.points)),
    1e-9,
  );

  return (
    <Card title="Score Drivers" subtitle="SHAP contributions, log-odds units">
      <div className="text-xs font-semibold uppercase tracking-wide text-emerald">
        Positive impactors
      </div>
      <div className="mt-2 space-y-2.5">
        {positive.length === 0 && (
          <p className="text-xs text-ink-muted">none in the stored reason codes</p>
        )}
        {positive.map((driver) => (
          <DriverRow key={driver.label} driver={driver} maxAbs={maxAbs} />
        ))}
      </div>

      <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-negative">
        Negative impactors
      </div>
      <div className="mt-2 space-y-2.5">
        {negative.length === 0 && (
          <p className="text-xs text-ink-muted">none in the stored reason codes</p>
        )}
        {negative.map((driver) => (
          <DriverRow key={driver.label} driver={driver} maxAbs={maxAbs} />
        ))}
      </div>

      <p className="mt-4 rounded-xl bg-sage p-3 text-xs leading-relaxed text-ink-soft">
        <span className="font-semibold text-ink">Reasoning: </span>
        {reasoning}
      </p>

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          onClick={onExport}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl border border-line px-3 py-2.5 text-sm font-medium text-ink-soft transition-colors hover:bg-sage"
        >
          <Download size={15} strokeWidth={1.8} />
          Export Audit Log
        </button>
        {onToggleReviewed && (
          <button
            type="button"
            disabled={busy}
            onClick={onToggleReviewed}
            className={`inline-flex flex-1 items-center justify-center gap-2 rounded-xl px-3 py-2.5 text-sm font-semibold transition-colors disabled:opacity-60 ${
              reviewed
                ? "border border-line bg-mint text-forest-deep hover:bg-sage"
                : "bg-forest text-white hover:bg-forest-deep"
            }`}
          >
            {reviewed ? (
              <RotateCcw size={15} strokeWidth={1.8} />
            ) : (
              <CheckCheck size={15} strokeWidth={1.8} />
            )}
            {reviewed ? "Reviewed — Unmark" : "Mark Reviewed"}
          </button>
        )}
      </div>
      {onToggleReviewed && (
        <p className="mt-2 text-center text-[11px] text-ink-muted">
          Records analyst review with an audit note. No credit decision is made
          here.
        </p>
      )}
    </Card>
  );
}

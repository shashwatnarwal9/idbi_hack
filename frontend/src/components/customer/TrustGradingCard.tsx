import type { ConfidenceBand } from "../../mocks/types";
import { Card } from "../Card";
import { ProgressBar } from "../ProgressBar";

const BAND_DOT: Record<ConfidenceBand, string> = {
  high: "bg-emerald",
  medium: "bg-amber",
  low: "bg-negative",
};

const BAND_TEXT: Record<ConfidenceBand, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

interface TrustGradingCardProps {
  band: ConfidenceBand;
  monthsHistory: number;
  /** Fraction in [0, 1] of transactions parsed with high confidence. */
  parseQuality: number;
}

export function TrustGradingCard({
  band,
  monthsHistory,
  parseQuality,
}: TrustGradingCardProps) {
  return (
    <Card title="Trust Grading" subtitle="How much this estimate can be trusted">
      <div className="flex items-center gap-2">
        <span className={`size-2.5 rounded-full ${BAND_DOT[band]}`} />
        <span className="text-sm font-semibold">{BAND_TEXT[band]}</span>
      </div>

      <dl className="mt-4 space-y-4">
        <div>
          <div className="flex items-baseline justify-between">
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              History length
            </dt>
            <dd className="text-sm font-semibold">{monthsHistory} months</dd>
          </div>
          <div className="mt-1.5">
            <ProgressBar value={Math.min(monthsHistory / 24, 1)} tone="brand" />
          </div>
        </div>
        <div>
          <div className="flex items-baseline justify-between">
            <dt className="text-xs font-medium uppercase tracking-wide text-ink-muted">
              Parse quality
            </dt>
            <dd className="text-sm font-semibold">
              {Math.round(parseQuality * 100)}%
            </dd>
          </div>
          <div className="mt-1.5">
            <ProgressBar value={parseQuality} tone="positive" />
          </div>
        </div>
      </dl>
    </Card>
  );
}

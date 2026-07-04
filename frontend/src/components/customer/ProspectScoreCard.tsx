import { Card } from "../Card";
import { DonutGauge } from "../DonutGauge";

interface ProspectScoreCardProps {
  /** Score on the 0-100 scale. */
  score: number;
  /** Qualitative reading, e.g. "Strong prospect". */
  scoreLabel: string;
}

export function ProspectScoreCard({ score, scoreLabel }: ProspectScoreCardProps) {
  return (
    <Card title="Prospect Score" subtitle="Model probability, scaled to 100">
      <div className="flex flex-col items-center py-2">
        <DonutGauge value={score / 100} valueLabel={`${score}`} size={140} />
        <div className="mt-1 text-xs text-ink-muted">out of 100</div>
        <div className="mt-2 rounded-full bg-mint px-3 py-1 text-xs font-semibold text-forest-deep">
          {scoreLabel}
        </div>
      </div>
    </Card>
  );
}

import { CheckCheck, Download, RotateCcw } from "lucide-react";

import { Card } from "../Card";

interface ReviewActionsCardProps {
  reviewed: boolean;
  busy?: boolean;
  onExport?: () => void;
  onToggleReviewed?: () => void;
}

/** Audit export + analyst-review toggle (no credit decision is made here). */
export function ReviewActionsCard({
  reviewed,
  busy = false,
  onExport,
  onToggleReviewed,
}: ReviewActionsCardProps) {
  return (
    <Card title="Analyst review" subtitle="Audit export and review status">
      <div className="flex gap-2">
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

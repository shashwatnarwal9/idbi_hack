import { CheckCheck, Download, Loader, RotateCcw, Share2 } from "lucide-react";

import { Card } from "../Card";

interface ReviewActionsCardProps {
  reviewed: boolean;
  busy?: boolean;
  onExport?: () => void;
  onToggleReviewed?: () => void;
  /** Customer-share controls; omit onShare to hide the action (uploads). */
  onShare?: () => void;
  sharing?: boolean;
  lastSharedAt?: string | null;
}

function formatShared(iso: string): string {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

/** Audit export + analyst-review toggle (no credit decision is made here). */
export function ReviewActionsCard({
  reviewed,
  busy = false,
  onExport,
  onToggleReviewed,
  onShare,
  sharing = false,
  lastSharedAt,
}: ReviewActionsCardProps) {
  return (
    <Card title="Analyst review" subtitle="Audit export and review status">
      <div className="flex flex-wrap items-center gap-3">
        {onShare && (
          <button
            type="button"
            disabled={sharing}
            onClick={onShare}
            className="inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-forest-deep disabled:opacity-60"
          >
            {sharing ? (
              <Loader size={15} className="animate-spin" />
            ) : (
              <Share2 size={15} strokeWidth={1.8} />
            )}
            Share with Customer
          </button>
        )}
        {onShare && (
          <div className="text-xs text-ink-soft">
            {lastSharedAt
              ? `Customer summary last shared on ${formatShared(lastSharedAt)}.`
              : "Generates a plain-language summary PDF for the customer (no score or model details)."}
          </div>
        )}
        <button
          type="button"
          onClick={onExport}
          className="inline-flex flex-1 items-center justify-center gap-2 rounded-xl bg-forest px-3 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-forest-deep"
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

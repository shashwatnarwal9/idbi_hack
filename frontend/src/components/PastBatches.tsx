import { Check, Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { useState } from "react";

import { apiDelete, apiPatch, apiPost } from "../lib/api";
import type { BatchPhase, UploadBatch } from "../lib/apiTypes";
import { useApi, useInvalidateApi } from "../lib/useApi";
import { Card } from "./Card";
import { ErrorNote, Loading } from "./Feedback";
import { ValidationFailuresCard } from "./ValidationFailuresCard";

const PHASE_META: Record<
  BatchPhase,
  { label: string; className: string; solid: boolean }
> = {
  // Muted OUTLINE badge for isolated previews (not in the operational book).
  isolated_preview: {
    label: "Isolated preview",
    className: "border border-line bg-transparent text-ink-soft",
    solid: false,
  },
  // SOLID badge for a batch merged into the book.
  validated_merged: {
    label: "Merged",
    className: "bg-mint text-forest-deep",
    solid: true,
  },
  failed_gate: {
    label: "Failed gate",
    className: "bg-negative/10 text-negative",
    solid: true,
  },
  reverted: {
    label: "Rolled back",
    className: "bg-sage text-ink-muted",
    solid: false,
  },
};

function PhaseBadge({ phase }: { phase: BatchPhase }) {
  const meta = PHASE_META[phase] ?? PHASE_META.isolated_preview;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${meta.className}`}
    >
      {meta.label}
    </span>
  );
}

interface Props {
  /** Reopen the batch's isolated analysis view. */
  onReopen: (batch: UploadBatch) => void;
}

/**
 * "Past Batches", every analysed upload, newest first. Isolated previews live
 * here only; they never appear in Deep Analysis, Loan Assessment or any
 * operational count. Rows are clickable to reopen, renamable, and deletable
 * (a merged batch is rolled back via the existing revert path). The list
 * refetches when the parent invalidates the "/uploads" cache after an upload.
 */
export function PastBatches({ onReopen }: Props) {
  const { data, loading, error, reload } = useApi<UploadBatch[]>("/uploads");
  const invalidate = useInvalidateApi();
  const [editing, setEditing] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState<string | null>(null);

  const saveName = async (batch: UploadBatch) => {
    const name = draft.trim();
    if (name && name !== batch.name) {
      await apiPatch(`/uploads/${batch.batch_id}`, { name });
      invalidate("/uploads");
      reload();
    }
    setEditing(null);
  };

  const remove = async (batch: UploadBatch) => {
    const merged = batch.phase === "validated_merged";
    const msg = merged
      ? "Roll back this merged batch, removing its customers from the main book?"
      : "Delete this batch and its isolated analysis?";
    if (!window.confirm(msg)) return;
    setBusy(batch.batch_id);
    try {
      if (merged) {
        await apiPost(`/uploads/${batch.batch_id}/revert`, { merged_by: "analyst" });
        invalidate(); // main book changed
      } else {
        await apiDelete(`/uploads/${batch.batch_id}`);
      }
      invalidate("/uploads");
      reload();
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <Loading label="Loading past batches…" />;
  if (error) return <ErrorNote message={error} />;
  if (!data || data.length === 0) {
    return (
      <Card title="Past batches">
        <p className="py-4 text-sm text-ink-muted">
          No uploads yet. Analysed batches will appear here, isolated from the
          demo book until you validate and merge them.
        </p>
      </Card>
    );
  }

  return (
    <Card
      title="Past batches"
      subtitle="Every analysed upload, isolated from the demo book · newest first"
    >
      <ul className="divide-y divide-line">
        {data.map((batch) => (
          <li key={batch.batch_id} className="py-3">
           <div className="flex flex-wrap items-center gap-3">
            <div className="min-w-0 flex-1">
              {editing === batch.batch_id ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") void saveName(batch);
                      if (e.key === "Escape") setEditing(null);
                    }}
                    className="w-full max-w-xs rounded-lg border border-line px-2 py-1 text-sm"
                  />
                  <button
                    type="button"
                    aria-label="Save name"
                    onClick={() => void saveName(batch)}
                    className="rounded-lg p-1 text-forest hover:bg-sage"
                  >
                    <Check size={15} />
                  </button>
                  <button
                    type="button"
                    aria-label="Cancel rename"
                    onClick={() => setEditing(null)}
                    className="rounded-lg p-1 text-ink-muted hover:bg-sage"
                  >
                    <X size={15} />
                  </button>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => onReopen(batch)}
                  className="block max-w-full truncate text-left text-sm font-semibold text-ink hover:text-forest"
                  title="Reopen this batch"
                >
                  {batch.name}
                </button>
              )}
              <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-muted">
                <span>{new Date(batch.created_at).toLocaleString()}</span>
                <span>·</span>
                <span>{batch.uploaded_by ?? "analyst"}</span>
                <span>·</span>
                <span>
                  {batch.n_customers} customers · {batch.n_transactions} txns
                </span>
              </div>
            </div>

            <PhaseBadge phase={batch.phase} />

            <div className="flex items-center gap-1">
              <button
                type="button"
                aria-label="Rename batch"
                onClick={() => {
                  setEditing(batch.batch_id);
                  setDraft(batch.name);
                }}
                className="rounded-lg p-1.5 text-ink-muted hover:bg-sage hover:text-ink-soft"
              >
                <Pencil size={15} />
              </button>
              <button
                type="button"
                aria-label={
                  batch.phase === "validated_merged"
                    ? "Roll back batch"
                    : "Delete batch"
                }
                disabled={busy === batch.batch_id}
                onClick={() => void remove(batch)}
                className="rounded-lg p-1.5 text-negative hover:bg-negative/10 disabled:opacity-40"
              >
                {batch.phase === "validated_merged" ? (
                  <RotateCcw size={15} />
                ) : (
                  <Trash2 size={15} />
                )}
              </button>
            </div>
           </div>

            {batch.phase === "failed_gate" && batch.failure_reasons.length > 0 && (
              <div className="mt-2">
                <ValidationFailuresCard
                  failures={batch.failure_reasons}
                  title="Why this batch failed the gate"
                  subtitle="Hard expectations that did not pass"
                />
              </div>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}

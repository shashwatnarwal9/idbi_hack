import { CheckCircle2, Database, Loader, ShieldCheck, UploadCloud, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { apiPost, apiUpload } from "../lib/api";
import type { AnalyzeResult, MergeResult } from "../lib/apiTypes";
import { useInvalidateApi } from "../lib/useApi";

interface Props {
  onClose: () => void;
}

function FileSlot({
  label,
  hint,
  file,
  onPick,
}: {
  label: string;
  hint: string;
  file: File | null;
  onPick: (f: File | null) => void;
}) {
  return (
    <label className="block cursor-pointer rounded-xl border border-dashed border-line bg-white/70 p-3 text-sm hover:bg-sage/60">
      <div className="font-medium text-ink">{label}</div>
      <div className="text-xs text-ink-muted">{hint}</div>
      <input
        type="file"
        accept=".csv"
        onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        className="mt-2 block w-full text-xs"
      />
      {file && <div className="mt-1 text-xs text-forest">{file.name}</div>}
    </label>
  );
}

/** Centered upload overlay: 3 CSV slots + inline gate results + merge confirm. */
export function UploadModal({ onClose }: Props) {
  const invalidate = useInvalidateApi();
  const [customers, setCustomers] = useState<File | null>(null);
  const [transactions, setTransactions] = useState<File | null>(null);
  const [events, setEvents] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [merge, setMerge] = useState<MergeResult | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = async (path: string) => {
    if (!transactions) {
      setError("A transactions CSV is required.");
      return;
    }
    setBusy(true);
    setError(null);
    setMerge(null);
    try {
      const form = new FormData();
      form.append("transactions", transactions);
      if (customers) form.append("customers", customers);
      if (events) form.append("events", events);
      const res = await apiUpload<AnalyzeResult>(path, form);
      setResult(res);
      invalidate("/uploads");
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const doMerge = async () => {
    if (!result) return;
    setBusy(true);
    try {
      const res = await apiPost<MergeResult>(`/uploads/${result.batch_id}/merge`, {
        confirm: true,
        merged_by: "analyst",
      });
      setMerge(res);
      invalidate(); // main book changed
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const passed = result?.status === "passed";

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-forest-deep/40 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="max-h-[88vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-line bg-cream/95 p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">Upload &amp; Analyze</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="rounded-lg p-1 text-ink-muted hover:bg-sage"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-2">
          <FileSlot
            label="Customers CSV"
            hint="Optional, names & declared income"
            file={customers}
            onPick={setCustomers}
          />
          <FileSlot
            label="Transactions CSV (required)"
            hint="Bank narrations the pipeline reconstructs income from"
            file={transactions}
            onPick={setTransactions}
          />
          <FileSlot
            label="Events CSV"
            hint="Optional, marketing/engagement events (10% of intent)"
            file={events}
            onPick={setEvents}
          />
        </div>
        <p className="mt-2 text-xs text-ink-muted">
          Columns are matched by synonym.{" "}
          <a
            href={`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/uploads/schema`}
            target="_blank"
            rel="noreferrer"
            className="font-medium text-forest underline"
          >
            Required columns
          </a>
          .
        </p>

        {error && (
          <p className="mt-3 rounded-lg bg-negative/10 p-2 text-sm text-negative">{error}</p>
        )}

        <div className="mt-4 flex flex-wrap gap-2">
          <button
            type="button"
            disabled={!transactions || busy}
            onClick={() => void submit("/uploads/analyze")}
            className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-semibold text-ink-soft hover:bg-sage disabled:opacity-50"
          >
            {busy ? <Loader size={15} className="animate-spin" /> : <UploadCloud size={15} />}
            Analyze (isolated)
          </button>
          <button
            type="button"
            disabled={!transactions || busy}
            onClick={() => void submit("/uploads/ingest")}
            className="inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-2.5 text-sm font-semibold text-white hover:bg-forest-deep disabled:opacity-50"
          >
            {busy ? <Loader size={15} className="animate-spin" /> : <ShieldCheck size={15} />}
            Validate &amp; Ingest
          </button>
        </div>

        {result && (
          <div className="mt-4 space-y-2 rounded-xl border border-line bg-white p-3">
            <div className="flex items-center gap-2 text-sm">
              <span className="font-medium">Batch {result.batch_id}</span>
              <span className="text-ink-muted">
                · {result.customers} customers · {result.transactions_used} txns
              </span>
            </div>
            {result.gates?.suites.map((suite) => (
              <div key={suite.suite} className="flex items-start gap-2 text-sm">
                {suite.passed ? (
                  <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald" />
                ) : (
                  <XCircle size={15} className="mt-0.5 shrink-0 text-negative" />
                )}
                <div>
                  <span className="font-mono text-xs">{suite.suite}</span>{" "}
                  <span className="text-ink-muted">
                    {suite.passed
                      ? `${suite.checks} checks passed`
                      : `failed: ${suite.failed.join(", ")}`}
                  </span>
                </div>
              </div>
            ))}
            {result.issues.length > 0 && (
              <ul className="list-inside list-disc text-xs text-amber">
                {result.issues.map((i) => (
                  <li key={i}>{i}</li>
                ))}
              </ul>
            )}

            {passed && !merge && (
              <button
                type="button"
                disabled={busy}
                onClick={() => void doMerge()}
                className="mt-2 inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-2 text-sm font-semibold text-white hover:bg-forest-deep disabled:opacity-60"
              >
                <Database size={15} />
                Merge {result.customers} customers into the main book?
              </button>
            )}
            {merge && (
              <p className="rounded-lg bg-mint/50 p-2 text-sm text-forest-deep">
                Merged {merge.merged} customer(s) into the main book.
              </p>
            )}
            {result.status === "failed" && (
              <p className="rounded-lg bg-negative/5 p-2 text-xs text-negative">
                The batch did not clear the hard gates, so it was not scored and cannot
                be merged. Fix the flagged rows and re-upload.
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

import {
  ArrowLeft,
  CheckCircle2,
  Database,
  FileUp,
  Info,
  Loader,
  ShieldCheck,
  Trash2,
  Undo2,
  UploadCloud,
  XCircle,
} from "lucide-react";
import { useMemo, useState } from "react";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { CustomerProfileView } from "../components/customer/CustomerProfileView";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorNote, Loading } from "../components/Feedback";
import { PastBatches } from "../components/PastBatches";
import { SectionHeader } from "../components/SectionHeader";
import { StatCard } from "../components/StatCard";
import { ValidationFailuresCard } from "../components/ValidationFailuresCard";
import { apiDelete, apiPost, apiUpload } from "../lib/api";
import { downloadJson } from "../lib/download";
import type {
  AnalyzeResult,
  BatchSummary,
  CustomerAnalysis,
  GateResult,
  MergeResult,
  RankedCustomer,
  UploadBatch,
  ValidationFailure,
} from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi, useInvalidateApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

interface SchemaField {
  field: string;
  required: boolean;
  description: string;
}
interface SchemaDoc {
  transactions: SchemaField[];
  customers: SchemaField[];
}

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};
const AUTO = "__auto__";

async function readHeaders(file: File): Promise<string[]> {
  const text = await file.slice(0, 64 * 1024).text();
  const firstLine = text.split(/\r?\n/)[0] ?? "";
  return firstLine.split(",").map((h) => h.trim().replace(/^"|"$/g, ""));
}

function buildMapping(fields: SchemaField[], choices: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const f of fields) {
    const chosen = choices[f.field];
    if (chosen && chosen !== AUTO) out[f.field] = chosen;
  }
  return out;
}

/** One file drop + optional column-mapping panel. */
function FileMapper({
  label,
  required,
  fields,
  file,
  headers,
  choices,
  onPick,
  onChoose,
}: {
  label: string;
  required: boolean;
  fields: SchemaField[];
  file: File | null;
  headers: string[];
  choices: Record<string, string>;
  onPick: (f: File | null) => void;
  onChoose: (field: string, header: string) => void;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Card title={label} subtitle={required ? "Required CSV" : "Optional CSV"}>
      <label className="flex cursor-pointer items-center gap-3 rounded-xl border border-dashed border-line bg-cream px-4 py-4 hover:bg-sage">
        <FileUp size={18} className="text-forest" />
        <span className="text-sm">
          {file ? (
            <span className="font-medium">{file.name}</span>
          ) : (
            <span className="text-ink-muted">Choose a .csv file…</span>
          )}
        </span>
        <input
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(e) => onPick(e.target.files?.[0] ?? null)}
        />
      </label>

      {headers.length > 0 && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            className="text-xs font-medium text-forest hover:underline"
          >
            {open ? "Hide" : "Column mapping"} · {headers.length} columns detected
          </button>
          {open && (
            <div className="mt-3 space-y-2">
              {fields.map((f) => (
                <div key={f.field} className="flex items-center gap-2">
                  <span className="w-48 shrink-0 font-mono text-xs">
                    {f.field}
                    {f.required && <span className="text-negative"> *</span>}
                  </span>
                  <select
                    value={choices[f.field] ?? AUTO}
                    onChange={(e) => onChoose(f.field, e.target.value)}
                    className="flex-1 rounded-lg border border-line bg-white px-2 py-1.5 text-sm"
                  >
                    <option value={AUTO}>Auto-detect</option>
                    {headers.map((h) => (
                      <option key={h} value={h}>
                        {h}
                      </option>
                    ))}
                  </select>
                </div>
              ))}
              <p className="text-xs text-ink-muted">
                Leave as Auto-detect to let आय·AI match by column name.
              </p>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

/** Flatten a batch's GE gate result into the shared ValidationFailuresCard
 * shape, so a failed_gate batch looks identical to the Validation page. */
function gateFailures(gates: GateResult | null): ValidationFailure[] {
  if (!gates) return [];
  return gates.suites.flatMap((s) =>
    s.failed.map((name) => ({
      expectation_name: name,
      layer: s.suite,
      detail: `Hard ${s.suite} expectation failed on this batch.`,
      severity: "hard",
    })),
  );
}

/** Reopen a stored batch in the same isolated results view a fresh analysis
 * uses. Summary/ranked are refetched from the batch id, so only the envelope
 * fields BatchResults reads directly need reconstructing. */
function batchToResult(batch: UploadBatch): AnalyzeResult {
  return {
    batch_id: batch.batch_id,
    customers: batch.n_customers,
    transactions_used: batch.n_transactions,
    issues: [],
    status: batch.status,
    gates: batch.gates,
    history: [],
    min_history_months: batch.min_history_months,
  };
}

export function Upload() {
  const schema = useApi<SchemaDoc>("/uploads/schema");
  const invalidate = useInvalidateApi();
  const [txnFile, setTxnFile] = useState<File | null>(null);
  const [custFile, setCustFile] = useState<File | null>(null);
  const [txnHeaders, setTxnHeaders] = useState<string[]>([]);
  const [custHeaders, setCustHeaders] = useState<string[]>([]);
  const [txnChoices, setTxnChoices] = useState<Record<string, string>>({});
  const [custChoices, setCustChoices] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeResult | null>(null);

  const pickTxn = async (f: File | null) => {
    setTxnFile(f);
    setTxnHeaders(f ? await readHeaders(f) : []);
  };
  const pickCust = async (f: File | null) => {
    setCustFile(f);
    setCustHeaders(f ? await readHeaders(f) : []);
  };

  const submit = async (path: string) => {
    if (!txnFile || !schema.data) return;
    setBusy(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("transactions", txnFile);
      if (custFile) form.append("customers", custFile);
      const tm = buildMapping(schema.data.transactions, txnChoices);
      const cm = buildMapping(schema.data.customers, custChoices);
      if (Object.keys(tm).length) form.append("transactions_mapping", JSON.stringify(tm));
      if (custFile && Object.keys(cm).length)
        form.append("customers_mapping", JSON.stringify(cm));
      setResult(await apiUpload<AnalyzeResult>(path, form));
      invalidate("/uploads"); // new batch shows in Past Batches
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const discard = async () => {
    if (!result) return;
    await apiDelete(`/uploads/${result.batch_id}`);
    invalidate("/uploads");
    setResult(null);
    setTxnFile(null);
    setCustFile(null);
    setTxnHeaders([]);
    setCustHeaders([]);
  };

  if (result) {
    return (
      <BatchResults
        result={result}
        onDiscard={() => void discard()}
        onBack={() => setResult(null)}
      />
    );
  }

  return (
    <div className="space-y-5">
      <SectionHeader description="Run your own customers and transactions through the आय·AI pipeline" />

      <div className="flex items-start gap-3 rounded-2xl border border-line bg-mint/40 p-4 text-sm text-forest-deep">
        <Info size={17} className="mt-0.5 shrink-0" />
        <p>
          Uploaded data is analysed in an <strong>isolated batch</strong>, kept
          entirely separate from the demo book, and can be discarded at any time.
          Raw transactions are not persisted beyond the computed results. There
          is no ground truth in uploaded data, so accuracy is not measured — only
          reconstructed results, with parse-confidence flagging weak parses.
        </p>
      </div>

      {schema.loading && <Loading label="Loading schema…" />}
      {schema.error && <ErrorNote message={schema.error} />}

      {schema.data && (
        <>
          <div className="grid gap-5 md:grid-cols-2">
            <FileMapper
              label="Transactions"
              required
              fields={schema.data.transactions}
              file={txnFile}
              headers={txnHeaders}
              choices={txnChoices}
              onPick={(f) => void pickTxn(f)}
              onChoose={(field, header) =>
                setTxnChoices((c) => ({ ...c, [field]: header }))
              }
            />
            <FileMapper
              label="Customers"
              required={false}
              fields={schema.data.customers}
              file={custFile}
              headers={custHeaders}
              choices={custChoices}
              onPick={(f) => void pickCust(f)}
              onChoose={(field, header) =>
                setCustChoices((c) => ({ ...c, [field]: header }))
              }
            />
          </div>

          {error && <ErrorNote message={error} />}

          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              disabled={!txnFile || busy}
              onClick={() => void submit("/uploads/analyze")}
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-5 py-3 text-sm font-semibold text-ink-soft transition-colors hover:bg-sage disabled:opacity-50"
            >
              {busy ? <Loader size={16} className="animate-spin" /> : <UploadCloud size={16} />}
              Analyze (isolated)
            </button>
            <button
              type="button"
              disabled={!txnFile || busy}
              onClick={() => void submit("/uploads/ingest")}
              className="inline-flex items-center gap-2 rounded-xl bg-forest px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-forest-deep disabled:opacity-50"
            >
              {busy ? <Loader size={16} className="animate-spin" /> : <ShieldCheck size={16} />}
              Validate &amp; Ingest to Database
            </button>
          </div>
          <p className="text-xs text-ink-muted">
            <strong>Analyze</strong> runs the pipeline in an isolated preview.{" "}
            <strong>Validate &amp; Ingest</strong> enforces the 18-month history
            gate and the pipeline's quality gates; only a passing book can be
            merged permanently into the main database.
          </p>
        </>
      )}

      <PastBatches onReopen={(batch) => setResult(batchToResult(batch))} />
    </div>
  );
}

function GateAndMergePanel({
  result,
  onMerged,
}: {
  result: AnalyzeResult;
  onMerged: () => void;
}) {
  const [merge, setMerge] = useState<MergeResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const invalidate = useInvalidateApi();
  const passed = result.status === "passed";
  const merged = merge?.status === "merged";

  const doMerge = async () => {
    setBusy(true);
    setErr(null);
    try {
      setMerge(
        await apiPost<MergeResult>(`/uploads/${result.batch_id}/merge`, {
          confirm: true,
          merged_by: "analyst",
        }),
      );
      // Merge changed the main book: refresh every cached chart/table.
      invalidate();
      onMerged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const doRevert = async () => {
    setBusy(true);
    try {
      setMerge(
        await apiPost<MergeResult>(`/uploads/${result.batch_id}/revert`, {
          merged_by: "analyst",
        }),
      );
      // Rollback also changed the main book: refresh caches.
      invalidate();
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card
      title="Quality gates & merge"
      subtitle={`18-month history gate + pipeline GE gates · batch ${result.status}`}
    >
      <div className="mb-3 flex items-center gap-2">
        {passed ? (
          <Badge tone="success">
            <CheckCircle2 size={12} className="mr-1" />
            Gates passed
          </Badge>
        ) : (
          <Badge tone="danger">
            <XCircle size={12} className="mr-1" />
            Gates failed
          </Badge>
        )}
        {result.min_history_months && (
          <span className="text-xs text-ink-muted">
            every customer ≥ {result.min_history_months} months of history
          </span>
        )}
      </div>

      <ul className="space-y-1.5">
        {result.gates?.suites.map((s) => (
          <li key={s.suite} className="flex items-center gap-2 text-sm">
            {s.passed ? (
              <CheckCircle2 size={15} className="text-emerald" />
            ) : (
              <XCircle size={15} className="text-negative" />
            )}
            <span className="font-mono text-xs">{s.suite}</span>
            <span className="text-ink-muted">
              {s.passed
                ? `${s.checks} checks passed`
                : `failed: ${s.failed.join(", ")}`}
            </span>
          </li>
        ))}
      </ul>

      {err && <p className="mt-3 text-sm text-negative">{err}</p>}

      {passed && !merged && (
        <div className="mt-4 rounded-xl bg-mint/40 p-4">
          <p className="text-sm text-forest-deep">
            This batch cleared every gate. Merging permanently adds{" "}
            <strong>{result.customers}</strong> customer(s) to the main database,
            tagged <span className="font-mono">source=uploaded</span>. They join
            operational views but never the seeded accuracy metrics.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void doMerge()}
            className="mt-3 inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-2.5 text-sm font-semibold text-white hover:bg-forest-deep disabled:opacity-60"
          >
            {busy ? <Loader size={15} className="animate-spin" /> : <Database size={15} />}
            Merge {result.customers} validated customers into the main database
          </button>
        </div>
      )}

      {merged && (
        <div className="mt-4 rounded-xl bg-mint/40 p-4">
          <p className="text-sm text-forest-deep">
            Merged {merge?.merged} customer(s) into the main database
            {merge?.skipped_duplicates
              ? ` (${merge.skipped_duplicates} skipped as duplicates)`
              : ""}
            . This is reversible by batch.
          </p>
          <button
            type="button"
            disabled={busy}
            onClick={() => void doRevert()}
            className="mt-3 inline-flex items-center gap-2 rounded-xl border border-line bg-white px-4 py-2.5 text-sm font-medium text-ink-soft hover:bg-sage disabled:opacity-60"
          >
            <Undo2 size={15} />
            Revert this batch
          </button>
        </div>
      )}

      {!passed && (
        <p className="mt-4 rounded-xl bg-negative/5 p-3 text-sm text-ink-soft">
          The batch did not clear the hard gates, so it was not scored and cannot
          be merged. It is kept as a failed batch with the reasons above.
        </p>
      )}
    </Card>
  );
}

function BatchResults({
  result,
  onDiscard,
  onBack,
}: {
  result: AnalyzeResult;
  onDiscard: () => void;
  onBack: () => void;
}) {
  const base = `/uploads/${result.batch_id}`;
  const gated = result.status === "passed" || result.status === "failed";
  const summary = useApi<BatchSummary>(`${base}/summary`);
  const [selected, setSelected] = useState<ConfidenceBand[]>(["high", "medium", "low"]);
  const rankedPath = useMemo(() => {
    const params = new URLSearchParams();
    if (selected.length < 3) for (const b of selected) params.append("confidence", b);
    const qs = params.toString();
    return `${base}/ranked${qs ? `?${qs}` : ""}`;
  }, [base, selected]);
  const ranked = useApi<RankedCustomer[]>(selected.length ? rankedPath : null);
  const [openId, setOpenId] = useState<string | null>(null);

  const exportBatch = () => {
    downloadJson(`${result.batch_id}-analysis.json`, {
      batch: result,
      summary: summary.data,
      ranked: ranked.data,
    });
  };

  if (openId) {
    return (
      <UploadProfile
        base={base}
        customerId={openId}
        onBack={() => setOpenId(null)}
      />
    );
  }

  const columns: Column<RankedCustomer>[] = [
    { header: "#", align: "right", cell: (r) => <span>{r.rank}</span> },
    {
      header: "Customer",
      cell: (r) => (
        <div className="leading-tight">
          <div className="font-medium">{r.name}</div>
          <div className="font-mono text-xs text-ink-muted">{r.customer_id}</div>
        </div>
      ),
    },
    {
      header: "Score /100",
      align: "right",
      cell: (r) => <span className="font-semibold">{(r.score * 100).toFixed(1)}</span>,
    },
    { header: "Confidence", cell: (r) => <Badge tone={BAND_TONE[r.band]}>{r.band}</Badge> },
    {
      header: "Top signals",
      cell: (r) => (
        <div className="flex flex-wrap gap-1.5">
          {r.reasons.slice(0, 3).map((reason) => (
            <span
              key={reason.feature}
              className={`rounded-full px-2 py-0.5 font-mono text-[11px] ${
                reason.shap > 0 ? "bg-mint text-forest-deep" : "bg-negative/10 text-negative"
              }`}
            >
              {reason.shap > 0 ? "+" : "−"}
              {reason.feature}
            </span>
          ))}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Batch Analysis"
        description={`${result.batch_id} · isolated from the demo book`}
        actions={
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-4 py-2 text-sm font-medium text-ink-soft hover:bg-sage"
            >
              <ArrowLeft size={15} />
              Back
            </button>
            <button
              type="button"
              onClick={exportBatch}
              className="rounded-xl border border-line bg-white px-4 py-2 text-sm font-medium text-ink-soft hover:bg-sage"
            >
              Export Analysis
            </button>
            <button
              type="button"
              onClick={onDiscard}
              className="inline-flex items-center gap-2 rounded-xl border border-negative/30 bg-negative/5 px-4 py-2 text-sm font-medium text-negative hover:bg-negative/10"
            >
              <Trash2 size={15} />
              Discard batch
            </button>
          </div>
        }
      />

      {result.issues.length > 0 && (
        <div className="rounded-2xl border border-amber/30 bg-amber/5 p-4 text-sm text-ink-soft">
          <div className="mb-1 font-semibold text-amber">Validation notes</div>
          <ul className="list-inside list-disc space-y-0.5">
            {result.issues.map((issue) => (
              <li key={issue}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {gated && <GateAndMergePanel result={result} onMerged={() => {}} />}

      {result.status === "failed" && (
        <ValidationFailuresCard
          failures={gateFailures(result.gates)}
          title="Gate failures"
          subtitle="Hard expectations this batch did not clear — it cannot be merged"
        />
      )}

      {summary.loading && <Loading />}
      {summary.error && <ErrorNote message={summary.error} />}
      {summary.data && (
        <div className="grid gap-5 md:grid-cols-4">
          <StatCard label="Customers analyzed" value={String(summary.data.customers)} />
          <StatCard
            label="Avg reconstructed income"
            value={
              summary.data.avg_reconstructed !== null
                ? inr(summary.data.avg_reconstructed)
                : "unavailable"
            }
          />
          <StatCard
            label="Median surplus"
            value={
              summary.data.median_surplus !== null
                ? inr(summary.data.median_surplus)
                : "unavailable"
            }
          />
          <StatCard
            label="High-prospect customers"
            value={`${summary.data.high_prospects} / ${summary.data.customers}`}
            hint={`bands · ${summary.data.bands.high} high / ${summary.data.bands.medium} medium / ${summary.data.bands.low} low`}
          />
        </div>
      )}

      <Card
        title="Ranked prospects"
        subtitle="Uploaded customers by prospect score · click a row for the full profile"
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium uppercase tracking-wide text-ink-muted">
            Confidence band
          </span>
          {(["high", "medium", "low"] as ConfidenceBand[]).map((band) => (
            <button
              key={band}
              type="button"
              onClick={() =>
                setSelected((prev) =>
                  prev.includes(band) ? prev.filter((b) => b !== band) : [...prev, band],
                )
              }
              className={`rounded-full px-3 py-1 text-xs font-medium ${
                selected.includes(band)
                  ? "bg-forest text-white"
                  : "bg-sage text-ink-soft hover:bg-mint"
              }`}
            >
              {band}
            </button>
          ))}
        </div>
        {selected.length === 0 ? (
          <p className="py-6 text-center text-sm text-ink-muted">
            Select at least one confidence band.
          </p>
        ) : ranked.loading ? (
          <Loading />
        ) : ranked.error ? (
          <ErrorNote message={ranked.error} />
        ) : (
          <DataTable
            columns={columns}
            rows={ranked.data ?? []}
            rowKey={(r) => r.customer_id}
            onRowClick={(r) => setOpenId(r.customer_id)}
          />
        )}
      </Card>
    </div>
  );
}

function UploadProfile({
  base,
  customerId,
  onBack,
}: {
  base: string;
  customerId: string;
  onBack: () => void;
}) {
  const analysis = useApi<CustomerAnalysis>(`${base}/customers/${encodeURIComponent(customerId)}`);

  const exportProfile = () => {
    if (analysis.data) downloadJson(`${customerId}-analysis.json`, analysis.data);
  };

  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={onBack}
        className="inline-flex items-center gap-2 text-sm font-medium text-ink-soft hover:text-ink"
      >
        <ArrowLeft size={15} />
        Back to batch
      </button>
      {analysis.loading && <Loading />}
      {analysis.error && <ErrorNote message={analysis.error} />}
      {analysis.data && (
        <CustomerProfileView data={analysis.data} onExport={exportProfile} />
      )}
    </div>
  );
}

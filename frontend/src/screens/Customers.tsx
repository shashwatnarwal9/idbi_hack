import { CheckCircle2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { Card } from "../components/Card";
import { CustomerProfileView } from "../components/customer/CustomerProfileView";
import { ErrorNote, Loading } from "../components/Feedback";
import { apiGet, apiPost, apiPostFile } from "../lib/api";
import { downloadBlob, downloadJson } from "../lib/download";
import type {
  CustomerAnalysis,
  ReviewState,
  SearchResult,
} from "../lib/apiTypes";
import { useApi, useInvalidateApi } from "../lib/useApi";

function SearchBox({ onPick }: { onPick: (id: string) => void }) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!q.trim()) return;
    setError(null);
    try {
      setResults(await apiGet<SearchResult[]>(`/customers/search?q=${encodeURIComponent(q.trim())}`));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <Card title="Search customers" subtitle="Partial id or name, matched live">
      <div className="flex gap-2">
        <label className="flex flex-1 items-center gap-2 rounded-xl border border-line bg-cream px-3 py-2">
          <Search size={15} className="text-ink-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && void run()}
            placeholder="e.g. CUST00087 or Mehta"
            className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted"
          />
        </label>
        <button
          type="button"
          onClick={() => void run()}
          className="rounded-xl bg-forest px-4 py-2 text-sm font-semibold text-white hover:bg-forest-deep"
        >
          Search
        </button>
      </div>
      {error && <p className="mt-3 text-sm text-negative">{error}</p>}
      {results !== null && (
        <ul className="mt-3 divide-y divide-line/60">
          {results.length === 0 && (
            <li className="py-3 text-sm text-ink-muted">
              No customers match “{q.trim()}”.
            </li>
          )}
          {results.map((r) => (
            <li key={r.customer_id}>
              <button
                type="button"
                onClick={() => onPick(r.customer_id)}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2.5 text-left hover:bg-sage"
              >
                <span className="font-mono text-xs text-ink-muted">
                  {r.customer_id}
                </span>
                <span className="text-sm font-medium">{r.name}</span>
                <span className="ml-auto flex items-center gap-2 text-xs text-ink-soft">
                  {r.reviewed && (
                    <CheckCircle2 size={14} className="text-emerald" />
                  )}
                  {r.band}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function Customers() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const analysis = useApi<CustomerAnalysis>(
    id ? `/customers/${encodeURIComponent(id)}` : null,
  );
  const [review, setReview] = useState<ReviewState | null>(null);
  const [busy, setBusy] = useState(false);
  const [sharing, setSharing] = useState(false);
  const invalidate = useInvalidateApi();
  useEffect(() => {
    setReview(analysis.data?.review ?? null);
  }, [analysis.data]);

  const pick = (customerId: string) => setParams({ id: customerId });

  const share = async () => {
    if (!id) return;
    setSharing(true);
    try {
      const { blob, filename } = await apiPostFile(
        `/customers/${encodeURIComponent(id)}/share`,
      );
      downloadBlob(filename, blob);
      analysis.reload(); // pick up the newly recorded share date from the server
    } finally {
      setSharing(false);
    }
  };

  const toggleReviewed = async () => {
    if (!id || review === null) return;
    setBusy(true);
    try {
      const next = await apiPost<ReviewState & { customer_id: string }>(
        `/customers/${encodeURIComponent(id)}/review`,
        { reviewed: !review.reviewed, reviewed_by: "analyst" },
      );
      setReview(next);
      // Reviewed flag shows up in the ranked list — refresh those caches.
      invalidate("/customers");
    } finally {
      setBusy(false);
    }
  };

  const exportAudit = () => {
    if (analysis.data) downloadJson(`${id}-audit.json`, analysis.data);
  };

  return (
    <div className="space-y-5">
      <SearchBox onPick={pick} />

      {!id && (
        <Card>
          <p className="py-8 text-center text-sm text-ink-muted">
            Search above, or open a customer from Deep Analysis.
          </p>
        </Card>
      )}

      {id && analysis.loading && <Loading />}
      {id && analysis.error && (
        <ErrorNote
          message={
            analysis.error.includes("not found")
              ? `${analysis.error} — check the id and try again.`
              : analysis.error
          }
        />
      )}

      {id && analysis.data && (
        <CustomerProfileView
          data={analysis.data}
          review={review}
          busy={busy}
          onToggleReviewed={() => void toggleReviewed()}
          onExport={exportAudit}
          onShare={() => void share()}
          sharing={sharing}
          lastSharedAt={analysis.data.last_share?.shared_at ?? null}
          loanDetailsId={analysis.data.profile.customer_id}
        />
      )}
    </div>
  );
}

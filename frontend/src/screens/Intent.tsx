import { CheckCircle2, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { BackButton } from "../components/BackButton";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import type { CustomerIntent, IntentSearchResult } from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

const QUADRANT_LABEL: Record<string, string> = {
  act_now: "Act now",
  nurture: "Nurture",
  downsell: "Downsell",
  exclude: "Exclude",
};

const PRODUCTS = ["personal", "auto", "home", "mortgage"] as const;

/** The signature 90% behavioural / 10% engagement stacked bar. */
function CompositionBar({ data }: { data: CustomerIntent }) {
  const split = data.composition.split;
  const b = split.find((s) => s.part === "behavioral")?.contribution ?? 0;
  const e = split.find((s) => s.part === "engagement")?.contribution ?? 0;
  const total = Math.max(b + e, 0.0001);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-ink-muted">
        <span>Fused intent composition</span>
        <span>
          {data.engagement_used ? "90% behavioural · 10% engagement" : "behavioural only"}
        </span>
      </div>
      <div className="flex h-6 overflow-hidden rounded-lg">
        <div
          className="flex items-center justify-center bg-forest text-[10px] font-semibold text-white"
          style={{ width: `${(b / total) * 100}%` }}
          title={`behavioural ${b.toFixed(1)}`}
        >
          B {b.toFixed(0)}
        </div>
        {data.engagement_used && (
          <div
            className="flex items-center justify-center bg-emerald text-[10px] font-semibold text-white"
            style={{ width: `${(e / total) * 100}%` }}
            title={`engagement ${e.toFixed(1)}`}
          >
            E {e.toFixed(0)}
          </div>
        )}
      </div>
      {!data.engagement_used && (
        <p className="mt-1 text-xs text-amber">
          Engagement data unavailable, behavioural only.
        </p>
      )}
    </div>
  );
}

function CustomerIntentView({ id }: { id: string }) {
  const { data, loading, error } = useApi<CustomerIntent>(
    `/intent/${encodeURIComponent(id)}`,
  );
  if (loading) return <Loading />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const maxProduct = Math.max(...Object.values(data.per_product_intent), 1);

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold">{data.name}</span>
              <Badge tone={BAND_TONE[data.confidence_band]}>
                {data.confidence_band}
              </Badge>
              <Badge tone="brand">{QUADRANT_LABEL[data.quadrant] ?? data.quadrant}</Badge>
            </div>
            <div className="mt-0.5 font-mono text-xs text-ink-muted">
              {data.customer_id} · decile {data.intent_decile}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-3xl font-bold text-forest-deep">
              {data.intent.toFixed(1)}
            </div>
            <div className="text-xs text-ink-muted">fused intent /100</div>
          </div>
        </div>
        <div className="mt-4">
          <CompositionBar data={data} />
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Per-product intent" subtitle="Behavioural + event affinity">
          <div className="space-y-3">
            {PRODUCTS.map((p) => {
              const v = data.per_product_intent[p] ?? 0;
              return (
                <div key={p} className="flex items-center gap-3">
                  <span className="w-20 shrink-0 text-sm capitalize text-ink-soft">
                    {p}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-sage">
                    <div
                      className="h-full rounded-full bg-forest"
                      style={{ width: `${(v / maxProduct) * 100}%` }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right text-sm font-semibold">
                    {v.toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="space-y-5">
          <Card title="Best-fit loan" subtitle="Top eligible product by intent">
            {data.best_fit_product ? (
              <div>
                <div className="flex items-center gap-2 text-lg font-semibold capitalize">
                  <CheckCircle2 size={18} className="text-emerald" />
                  {data.best_fit_product}
                </div>
                <p className="mt-1 text-sm text-ink-soft">
                  {data.best_fit_reason ??
                    "Top per-product intent among products this customer qualifies for."}
                </p>
              </div>
            ) : (
              <p className="text-sm text-ink-muted">
                {data.best_fit_reason ?? "No product passes the eligibility gate."}
              </p>
            )}
          </Card>

          {data.best_repayable && (
            <Card title="Best repayable" subtitle="Affordable, capped by surplus & FOIR">
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-ink-soft">Affordable EMI</span>
                <span className="text-lg font-bold text-forest-deep">
                  {inr(data.best_repayable.affordable_emi)}/mo
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-sm text-ink-soft">
                  Max principal @ {data.best_repayable.annual_rate_pct}% ·{" "}
                  {data.best_repayable.tenure_months}mo
                </span>
                <span className="font-semibold">
                  {inr(data.best_repayable.max_principal)}
                </span>
              </div>
              <p className="mt-2 text-[11px] text-ink-muted">{data.disclaimer}</p>
            </Card>
          )}
        </div>
      </div>

      {data.engagement && (
        <Card title="Engagement" subtitle="Marketing events (10% of intent)">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <div className="text-xs text-ink-muted">Last event</div>
              <div className="font-medium">{data.engagement.last_event_type}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Sessions (90d)</div>
              <div className="font-medium">{data.engagement.sessions_90d}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Strongest action</div>
              <div className="font-medium">{data.engagement.strongest_action}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Offer click rate</div>
              <div className="font-medium">
                {Math.round(data.engagement.offer_click_rate * 100)}%
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

/** Search by NAME or cust id, with live suggestions from /intent/search. */
function SearchPanel() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 250);
    return () => clearTimeout(t);
  }, [query]);

  const results = useApi<IntentSearchResult[]>(
    debounced.length >= 1 ? `/intent/search?q=${encodeURIComponent(debounced)}` : null,
  );
  const go = (cid: string) => navigate(`/intent/${encodeURIComponent(cid)}`);

  return (
    <Card>
      <label className="flex items-center gap-2 rounded-xl border border-line bg-cream px-3 py-2">
        <Search size={15} className="text-ink-muted" />
        <input
          autoFocus
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && results.data && results.data.length > 0) {
              go(results.data[0].customer_id);
            }
          }}
          placeholder="Search by name (e.g. Meera Chopra) or cust id (e.g. CUST01001)…"
          className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted"
        />
      </label>

      {debounced.length >= 1 && (
        <div className="mt-3">
          {results.loading ? (
            <Loading />
          ) : results.error ? (
            <ErrorNote message={results.error} />
          ) : (results.data ?? []).length === 0 ? (
            <p className="py-3 text-sm text-ink-muted">No customer matches “{debounced}”.</p>
          ) : (
            <ul className="divide-y divide-line/60">
              {(results.data ?? []).map((r) => (
                <li key={r.customer_id}>
                  <button
                    type="button"
                    onClick={() => go(r.customer_id)}
                    className="flex w-full items-center gap-3 py-2.5 text-left hover:text-forest"
                  >
                    <span className="font-medium">{r.name}</span>
                    <span className="font-mono text-xs text-ink-muted">
                      {r.customer_id}
                    </span>
                    <span className="ml-auto text-sm font-semibold">
                      {r.intent.toFixed(0)}
                    </span>
                    <Badge tone="brand">
                      {QUADRANT_LABEL[r.quadrant] ?? r.quadrant}
                    </Badge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}

export function Intent() {
  const { customerId } = useParams();

  if (customerId) {
    return (
      <div className="space-y-5">
        <BackButton />
        <CustomerIntentView id={customerId} />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <SectionHeader description="Fused purchase intent, 90% behavioural, 10% engagement" />
      <SearchPanel />
      <p className="text-sm text-ink-muted">
        Search a customer above, or open one from Leads or an Overview quadrant.
      </p>
    </div>
  );
}

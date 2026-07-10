import { ArrowLeft, CheckCircle2, ExternalLink, XCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import type { CustomerAnalysis, LoanCalcResponse } from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

/** Per-product default terms, the single source for rates and tenures. */
const PRODUCT_TERMS: {
  key: string;
  label: string;
  defaultRate: number;
  defaultTenure: number;
}[] = [
  { key: "personal", label: "Personal Loan", defaultRate: 11, defaultTenure: 36 },
  { key: "auto", label: "Auto Loan", defaultRate: 9.5, defaultTenure: 60 },
  { key: "home", label: "Home Loan", defaultRate: 8.5, defaultTenure: 180 },
  { key: "mortgage", label: "Mortgage Loan", defaultRate: 8.5, defaultTenure: 240 },
];

const RATE_BOUNDS = { min: 0, max: 40 };
const TENURE_BOUNDS = { min: 6, max: 360 };
const DEBOUNCE_MS = 300;

interface Terms {
  rate: string;
  tenure: string;
}

type TermsByProduct = Record<string, Terms>;

const DEFAULT_TERMS: TermsByProduct = Object.fromEntries(
  PRODUCT_TERMS.map((p) => [
    p.key,
    { rate: String(p.defaultRate), tenure: String(p.defaultTenure) },
  ]),
);

function parseRate(raw: string): number | null {
  const v = Number(raw);
  return raw.trim() !== "" && Number.isFinite(v) && v >= RATE_BOUNDS.min && v <= RATE_BOUNDS.max
    ? v
    : null;
}

function parseTenure(raw: string): number | null {
  const v = Number(raw);
  return raw.trim() !== "" &&
    Number.isInteger(v) &&
    v >= TENURE_BOUNDS.min &&
    v <= TENURE_BOUNDS.max
    ? v
    : null;
}

function parseAmount(raw: string): number | null {
  if (raw.trim() === "") return null; // empty is fine: no requested amount
  const v = Number(raw);
  return Number.isFinite(v) && v > 0 ? v : null;
}

function calcPath(
  customerId: string,
  product: string,
  rate: number,
  tenure: number,
  amount: number | null,
): string {
  const params = new URLSearchParams({
    product,
    annual_rate: String(rate),
    tenure_months: String(tenure),
  });
  if (amount !== null) params.set("amount", String(amount));
  return `/customers/${encodeURIComponent(customerId)}/loan-calc?${params.toString()}`;
}

function VerdictPill({ status }: { status: "eligible" | "not_eligible" }) {
  return status === "eligible" ? (
    <span className="inline-flex items-center gap-1 rounded-full bg-mint px-2.5 py-0.5 text-xs font-semibold text-forest-deep">
      <CheckCircle2 size={12} />
      Eligible
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 rounded-full bg-negative/10 px-2.5 py-0.5 text-xs font-semibold text-negative">
      <XCircle size={12} />
      Not eligible
    </span>
  );
}

function ProductCard({
  customerId,
  product,
  terms,
  debouncedTerms,
  amount,
  amountEntered,
  onTermsChange,
}: {
  customerId: string;
  product: (typeof PRODUCT_TERMS)[number];
  /** Live values for the inputs, no typing lag. */
  terms: Terms;
  /** Debounced values for the request, so we fetch after typing settles. */
  debouncedTerms: Terms;
  amount: number | null;
  amountEntered: boolean;
  onTermsChange: (field: keyof Terms, value: string) => void;
}) {
  const rate = parseRate(debouncedTerms.rate);
  const tenure = parseTenure(debouncedTerms.tenure);
  const valid = rate !== null && tenure !== null;
  const path = valid ? calcPath(customerId, product.key, rate, tenure, amount) : null;
  const { data, error, loading } = useApi<LoanCalcResponse>(path);

  const gateFailed = data?.base_eligibility.status === "not_eligible";

  return (
    <Card title={product.label}>
      <div className="mb-3 flex flex-wrap items-end gap-3">
        <label className="text-xs text-ink-soft">
          <span className="mb-1 block">Rate (% p.a.)</span>
          <input
            type="number"
            step={0.1}
            min={RATE_BOUNDS.min}
            max={RATE_BOUNDS.max}
            value={terms.rate}
            onChange={(e) => onTermsChange("rate", e.target.value)}
            className="w-24 rounded-lg border border-line bg-cream px-3 py-1.5 text-sm outline-none"
          />
        </label>
        <label className="text-xs text-ink-soft">
          <span className="mb-1 block">Tenure (months)</span>
          <input
            type="number"
            step={1}
            min={TENURE_BOUNDS.min}
            max={TENURE_BOUNDS.max}
            value={terms.tenure}
            onChange={(e) => onTermsChange("tenure", e.target.value)}
            className="w-24 rounded-lg border border-line bg-cream px-3 py-1.5 text-sm outline-none"
          />
        </label>
        {data?.requested && <VerdictPill status={data.requested.status} />}
      </div>

      {!valid ? (
        <p className="py-3 text-sm text-ink-muted">
          Enter a rate between {RATE_BOUNDS.min}–{RATE_BOUNDS.max}% and a tenure
          between {TENURE_BOUNDS.min}–{TENURE_BOUNDS.max} months.
        </p>
      ) : loading ? (
        <Loading />
      ) : error ? (
        <ErrorNote message={error} />
      ) : data ? (
        <>
          <div className="mb-1 text-xs font-medium uppercase tracking-wide text-ink-muted">
            Max eligible loan
          </div>
          <div
            className={`text-2xl font-bold ${
              data.affordability.max_loan_amount > 0 ? "text-forest-deep" : "text-negative"
            }`}
          >
            {inr(data.affordability.max_loan_amount)}
          </div>
          <div className="mt-1 text-xs text-ink-muted">
            at {data.terms.annual_rate_pct}% over {data.terms.tenure_months} months
            {data.affordability.binding_cap &&
              ` · headroom ${inr(data.affordability.affordable_emi)}/mo (${data.affordability.binding_cap} cap)`}
          </div>

          {data.requested && (
            <dl className="mt-3 space-y-1 border-t border-line pt-3 text-sm">
              <div className="flex justify-between">
                <dt className="text-ink-soft">EMI for {inr(data.requested.amount)}</dt>
                <dd className="font-semibold">{inr(data.requested.emi)}/mo</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-soft">Total repayment</dt>
                <dd>{inr(data.requested.total_repayment)}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-soft">Total interest</dt>
                <dd>{inr(data.requested.total_interest)}</dd>
              </div>
              {data.requested.post_loan_dti !== null && (
                <div className="flex justify-between">
                  <dt className="text-ink-soft">Post-loan obligations</dt>
                  <dd>{Math.round(data.requested.post_loan_dti * 100)}% of income</dd>
                </div>
              )}
            </dl>
          )}

          {gateFailed && (
            <p className="mt-3 rounded-xl bg-negative/5 p-3 text-xs leading-relaxed text-negative">
              <span className="font-semibold">Does not qualify: </span>
              {data.base_eligibility.reason}
            </p>
          )}
          {!gateFailed &&
            data.requested &&
            data.requested.status === "not_eligible" && (
              <ul className="mt-3 space-y-1 rounded-xl bg-negative/5 p-3 text-xs leading-relaxed text-negative">
                {data.requested.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
          {!data.requested && amountEntered && (
            <p className="mt-3 text-xs text-ink-muted">
              Enter a loan amount above 0 to check a specific amount.
            </p>
          )}

          <p className="mt-3 text-[11px] leading-relaxed text-ink-muted">
            {data.disclaimer}
          </p>
        </>
      ) : null}
    </Card>
  );
}

/** Per-customer loan calculator: one shared amount, all four products compared. */
export function LoanDetails() {
  const { customerId = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  // When we arrived from a customer profile (Loan Eligibility card), Back should
  // return there; otherwise fall back to the Loan Assessment list.
  const fromCustomer =
    (location.state as { from?: string } | null)?.from === "customer";
  const backTo = fromCustomer
    ? `/customers?id=${encodeURIComponent(customerId)}`
    : "/loan-assessment";
  const backLabel = fromCustomer ? "Back to customer" : "Back to Loan Assessment";
  const analysis = useApi<CustomerAnalysis>(
    customerId ? `/customers/${encodeURIComponent(customerId)}` : null,
  );

  const [amountRaw, setAmountRaw] = useState("");
  const [termsByProduct, setTermsByProduct] = useState<TermsByProduct>(DEFAULT_TERMS);

  // Debounce the inputs so the four product requests fire ~300ms after typing
  // stops rather than on every keystroke.
  const [debounced, setDebounced] = useState({
    amountRaw,
    termsByProduct,
  });
  useEffect(() => {
    const t = setTimeout(
      () => setDebounced({ amountRaw, termsByProduct }),
      DEBOUNCE_MS,
    );
    return () => clearTimeout(t);
  }, [amountRaw, termsByProduct]);

  const amount = useMemo(() => parseAmount(debounced.amountRaw), [debounced.amountRaw]);
  const amountEntered = debounced.amountRaw.trim() !== "";

  const p = analysis.data?.profile;
  const score = analysis.data?.score;

  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={() => navigate(backTo)}
        className="inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3.5 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-sage"
      >
        <ArrowLeft size={15} strokeWidth={1.8} />
        {backLabel}
      </button>

      {analysis.loading && <Loading label="Loading customer…" />}
      {analysis.error && <ErrorNote message={analysis.error} />}

      {p && (
        <>
          <SectionHeader
            description={`Loan calculator for ${p.name}, qualification from the product rules, affordability from reconstructed income`}
          />

          <Card>
            <div className="flex flex-wrap items-center gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold">{p.name}</span>
                  <Badge tone={BAND_TONE[p.confidence_band]}>{p.confidence_band}</Badge>
                </div>
                <div className="mt-0.5 flex items-center gap-2 font-mono text-xs text-ink-muted">
                  {p.customer_id}
                  <Link
                    to={`/customers?id=${encodeURIComponent(p.customer_id)}`}
                    className="inline-flex items-center gap-1 not-italic text-forest underline"
                  >
                    full profile
                    <ExternalLink size={11} />
                  </Link>
                </div>
              </div>
              <div className="ml-auto grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-4">
                <div>
                  <div className="text-xs text-ink-muted">Score /100</div>
                  <div className="font-semibold">
                    {score ? (score.p_good_prospect * 100).toFixed(1) : "unavailable"}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-ink-muted">Monthly income</div>
                  <div className="font-semibold">{inr(p.true_monthly_income)}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-muted">Investable surplus</div>
                  <div className="font-semibold">{inr(p.investable_surplus)}</div>
                </div>
                <div>
                  <div className="text-xs text-ink-muted">Existing EMIs</div>
                  <div className="font-semibold">{inr(p.total_emi)}/mo</div>
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <label className="text-sm font-medium text-ink">
              Loan amount (₹)
              <div className="mt-1.5 flex flex-wrap items-center gap-3">
                <input
                  type="number"
                  min={1}
                  value={amountRaw}
                  onChange={(e) => setAmountRaw(e.target.value)}
                  placeholder="e.g. 2500000"
                  className="w-56 rounded-xl border border-line bg-cream px-3.5 py-2.5 text-sm outline-none"
                />
                {amount !== null && (
                  <span className="text-sm text-ink-soft">= {inr(amount)}</span>
                )}
                {amountEntered && amount === null && (
                  <span className="text-sm text-negative">
                    Enter an amount above 0.
                  </span>
                )}
              </div>
            </label>
            <p className="mt-2 text-xs text-ink-muted">
              One amount, compared across all four products below. Rates and
              tenures are editable per product. Amounts are illustrative, not
              offers.
            </p>
          </Card>

          <div className="grid gap-5 md:grid-cols-2">
            {PRODUCT_TERMS.map((product) => (
              <ProductCard
                key={product.key}
                customerId={customerId}
                product={product}
                terms={termsByProduct[product.key]}
                debouncedTerms={debounced.termsByProduct[product.key]}
                amount={amount}
                amountEntered={amountEntered}
                onTermsChange={(field, value) =>
                  setTermsByProduct((prev) => ({
                    ...prev,
                    [product.key]: { ...prev[product.key], [field]: value },
                  }))
                }
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}

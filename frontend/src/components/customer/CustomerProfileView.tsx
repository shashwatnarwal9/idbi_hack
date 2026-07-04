import { Loader, Share2 } from "lucide-react";

import type { CustomerAnalysis, ReviewState } from "../../lib/apiTypes";
import { IncomeReconstructionCard } from "./IncomeReconstructionCard";
import { InvestableSurplusCard } from "./InvestableSurplusCard";
import { KeyTransactionsList } from "./KeyTransactionsList";
import { LoanEligibilityCard } from "./LoanEligibilityCard";
import { ProfileHeader } from "./ProfileHeader";
import { ProspectScoreCard } from "./ProspectScoreCard";
import { ScoreDriversCard } from "./ScoreDriversCard";
import { TrustGradingCard } from "./TrustGradingCard";

const STREAM_LABELS: Record<string, string> = {
  salary: "Salary income",
  gig_income: "Gig payouts",
  business_income: "Business receipts",
  interest: "Interest",
};

function monthYear(iso: string | null): string {
  if (!iso) return "unavailable";
  return new Date(iso).toLocaleDateString("en-IN", {
    month: "short",
    year: "numeric",
  });
}

function scoreLabel(p: number): string {
  if (p >= 0.7) return "Strong prospect";
  if (p >= 0.4) return "Borderline";
  return "Weak prospect";
}

interface CustomerProfileViewProps {
  data: CustomerAnalysis;
  onExport: () => void;
  /** Review controls; omit onToggleReviewed to hide the review action (uploads). */
  review?: ReviewState | null;
  busy?: boolean;
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

/** The full per-customer analysis, shared by the seeded and upload screens. */
export function CustomerProfileView({
  data,
  onExport,
  review = null,
  busy = false,
  onToggleReviewed,
  onShare,
  sharing = false,
  lastSharedAt,
}: CustomerProfileViewProps) {
  const p = data.profile;
  const sb = data.surplus_breakdown;
  const reasons = data.score?.reasons ?? [];
  const positive = reasons
    .filter((r) => r.shap > 0)
    .map((r) => ({ label: r.feature, points: r.shap }));
  const negative = reasons
    .filter((r) => r.shap <= 0)
    .map((r) => ({ label: r.feature, points: r.shap }));
  const surplusRatio = sb.income > 0 ? sb.surplus / sb.income : 0;
  const reasoning =
    positive.length || negative.length
      ? `Pushed up by ${positive.map((d) => d.label).join(", ") || "nothing"}; ` +
        `held back by ${negative.map((d) => d.label).join(", ") || "nothing"}.`
      : "No stored reason codes for this customer.";

  return (
    <>
      <ProfileHeader
        name={p.name}
        customerId={p.customer_id}
        memberSince={monthYear(p.account_open_date)}
        location={p.region ?? "unavailable"}
        occupation={p.occupation_declared ?? "unavailable"}
      />

      {onShare && (
        <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-line bg-white p-4 shadow-sm">
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
          <div className="text-xs text-ink-soft">
            {lastSharedAt
              ? `Customer summary last shared on ${formatShared(lastSharedAt)}.`
              : "Generates a plain-language summary PDF for the customer (no score or model details)."}
          </div>
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <IncomeReconstructionCard
            declaredMonthly={p.declared_monthly_income}
            reconstructedMonthly={p.true_monthly_income}
            streams={data.income_streams.map((s) => ({
              label: STREAM_LABELS[s.category] ?? s.category,
              sharePct: Math.round(s.share * 100),
              note: `Seen in ${s.months_seen} of ${p.months_history} months · avg ₹${Math.round(s.avg_monthly).toLocaleString("en-IN")}/mo`,
            }))}
          />
          <InvestableSurplusCard
            lines={[
              { label: "Total income", amount: sb.income },
              { label: "Essentials", amount: -sb.essentials },
              { label: "EMIs", amount: -sb.emis },
              { label: "Safety buffer", amount: -sb.buffer },
            ]}
            surplus={sb.surplus}
            savingsTitle={
              surplusRatio >= 0.25 ? "High saving potential" : "Limited saving potential"
            }
            savingsNote={`Surplus is ${Math.round(surplusRatio * 100)}% of reconstructed income.`}
          />
          <KeyTransactionsList
            transactions={data.key_transactions.map((t) => ({
              id: t.txn_id,
              label: t.label,
              meta: `${t.date} · ${t.channel} · ${t.category}`,
              amount: t.direction === "credit" ? t.amount : -t.amount,
              category: t.category,
            }))}
          />
        </div>

        <div className="space-y-5">
          <ProspectScoreCard
            score={Math.round((data.score?.p_good_prospect ?? 0) * 100)}
            scoreLabel={
              data.score ? scoreLabel(data.score.p_good_prospect) : "unavailable"
            }
          />
          <TrustGradingCard
            band={p.confidence_band}
            monthsHistory={p.months_history}
            parseQuality={p.pct_categorized}
          />
          <LoanEligibilityCard products={data.loan_eligibility ?? []} />
          <ScoreDriversCard
            positive={positive}
            negative={negative}
            reasoning={reasoning}
            reviewed={review?.reviewed ?? false}
            busy={busy}
            onToggleReviewed={onToggleReviewed}
            onExport={onExport}
          />
        </div>
      </div>
    </>
  );
}

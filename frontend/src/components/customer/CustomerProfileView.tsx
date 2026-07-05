import type { CustomerAnalysis, ReviewState } from "../../lib/apiTypes";
import { IncomeReconstructionCard } from "./IncomeReconstructionCard";
import { InvestableSurplusCard } from "./InvestableSurplusCard";
import { KeyTransactionsList } from "./KeyTransactionsList";
import { LoanEligibilityCard } from "./LoanEligibilityCard";
import { ProfileHeader } from "./ProfileHeader";
import { ProspectScoreCard } from "./ProspectScoreCard";
import { ReviewActionsCard } from "./ReviewActionsCard";

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
  /** When set, the Loan Eligibility card shows a "View loan details" link to
   * this customer's calculator (seeded/merged customers only, not batch previews). */
  loanDetailsId?: string;
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
  loanDetailsId,
}: CustomerProfileViewProps) {
  const p = data.profile;
  const sb = data.surplus_breakdown;
  const surplusRatio = sb.income > 0 ? sb.surplus / sb.income : 0;

  return (
    <>
      <ProfileHeader
        name={p.name}
        customerId={p.customer_id}
        memberSince={monthYear(p.account_open_date)}
        location={p.region ?? "unavailable"}
        occupation={p.occupation_declared ?? "unavailable"}
      />

      {/* Flat grid: each card is its own grid item, so the two cards in a row
          share equal height (grid's default align-items: stretch). Row-major
          order keeps the same left/right arrangement as before. */}
      <div className="grid items-stretch gap-5 lg:grid-cols-2">
        <IncomeReconstructionCard
          declaredMonthly={p.declared_monthly_income}
          reconstructedMonthly={p.true_monthly_income}
          streams={data.income_streams.map((s) => ({
            label: STREAM_LABELS[s.category] ?? s.category,
            sharePct: Math.round(s.share * 100),
            note: `Seen in ${s.months_seen} of ${p.months_history} months · avg ₹${Math.round(s.avg_monthly).toLocaleString("en-IN")}/mo`,
          }))}
        />
        <ProspectScoreCard
          score={Math.round((data.score?.p_good_prospect ?? 0) * 100)}
          scoreLabel={
            data.score ? scoreLabel(data.score.p_good_prospect) : "unavailable"
          }
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
        <LoanEligibilityCard
          products={data.loan_eligibility ?? []}
          customerId={loanDetailsId}
        />
      </div>

      <KeyTransactionsList
        transactions={data.key_transactions.map((t) => ({
          id: t.txn_id,
          label: t.label,
          meta: `${t.date} · ${t.channel} · ${t.category}`,
          amount: t.direction === "credit" ? t.amount : -t.amount,
          category: t.category,
        }))}
      />

      <ReviewActionsCard
        reviewed={review?.reviewed ?? false}
        busy={busy}
        onToggleReviewed={onToggleReviewed}
        onExport={onExport}
        onShare={onShare}
        sharing={sharing}
        lastSharedAt={lastSharedAt}
      />
    </>
  );
}

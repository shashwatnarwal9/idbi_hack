import { ArrowRight } from "lucide-react";
import { useNavigate } from "react-router-dom";

import type { LoanEligibility } from "../../lib/apiTypes";
import { Card } from "../Card";
import { DonutGauge } from "../DonutGauge";

interface LoanEligibilityCardProps {
  products: LoanEligibility[];
  /** When set, show a "View loan details" link to that customer's calculator. */
  customerId?: string;
}

/** Eligible/total donut summary with a link to the full per-product calculator. */
export function LoanEligibilityCard({ products, customerId }: LoanEligibilityCardProps) {
  const navigate = useNavigate();
  const total = products.length;
  const eligibleCount = products.filter((p) => p.status === "eligible").length;

  return (
    <Card title="Loan Eligibility" subtitle="Rule-based on income, stability & history">
      {total > 0 && (
        <div className="flex flex-col items-center gap-3">
          <DonutGauge
            value={eligibleCount / total}
            valueLabel={`${eligibleCount}/${total}`}
            label="eligible"
          />
          {customerId && (
            <button
              type="button"
              onClick={() =>
                navigate(`/loan-assessment/${encodeURIComponent(customerId)}`, {
                  state: { from: "customer", customerId },
                })
              }
              className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-white px-3.5 py-2 text-sm font-medium text-ink-soft transition-colors hover:bg-sage"
            >
              View loan details
              <ArrowRight size={15} strokeWidth={1.8} />
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

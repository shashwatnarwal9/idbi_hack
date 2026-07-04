import { Car, CheckCircle2, Home, Landmark, User, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { inr } from "../../lib/format";
import type { LoanEligibility } from "../../lib/apiTypes";
import { Card } from "../Card";

const ICONS: Record<string, LucideIcon> = {
  personal: User,
  auto: Car,
  home: Home,
  mortgage: Landmark,
};

interface LoanEligibilityCardProps {
  products: LoanEligibility[];
}

/** Compact per-product loan eligibility with reason or illustrative amount. */
export function LoanEligibilityCard({ products }: LoanEligibilityCardProps) {
  return (
    <Card title="Loan Eligibility" subtitle="Rule-based on income, stability & history">
      <ul className="divide-y divide-line/60">
        {products.map((p) => {
          const Icon = ICONS[p.product] ?? User;
          const eligible = p.status === "eligible";
          return (
            <li key={p.product} className="flex items-start gap-3 py-2.5">
              <div
                className={`mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-lg ${
                  eligible ? "bg-mint text-forest" : "bg-sage text-ink-muted"
                }`}
              >
                <Icon size={15} strokeWidth={1.8} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{p.label}</span>
                  {eligible ? (
                    <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald">
                      <CheckCircle2 size={13} />
                      Eligible
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-xs font-medium text-ink-muted">
                      <XCircle size={13} />
                      Not eligible
                    </span>
                  )}
                </div>
                {eligible && p.suggested_amount !== null ? (
                  <div className="mt-0.5 text-xs text-ink-soft">
                    Up to{" "}
                    <span className="font-semibold text-forest-deep">
                      {inr(p.suggested_amount)}
                    </span>{" "}
                    <span className="text-ink-muted">· illustrative, not an offer</span>
                  </div>
                ) : (
                  <div className="mt-0.5 text-xs text-ink-muted">{p.reason}</div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

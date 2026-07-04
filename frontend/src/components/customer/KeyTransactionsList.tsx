import {
  ArrowDownLeft,
  ArrowUpRight,
  Banknote,
  Bike,
  Briefcase,
  Clapperboard,
  Fuel,
  Home,
  Landmark,
  Percent,
  Plug,
  ReceiptText,
  ShoppingBag,
  ShoppingBasket,
  Store,
  TrendingUp,
  Utensils,
  type LucideIcon,
} from "lucide-react";

import { inr } from "../../lib/format";
import type { KeyTransaction } from "../../mocks/types";
import { Card } from "../Card";

const ICONS: Record<string, LucideIcon> = {
  salary: Briefcase,
  gig_income: Bike,
  business_income: Store,
  interest: Percent,
  rent: Home,
  emi: Landmark,
  sip: TrendingUp,
  utility: Plug,
  groceries: ShoppingBasket,
  food: Utensils,
  fuel: Fuel,
  shopping: ShoppingBag,
  entertainment: Clapperboard,
  p2p_in: ArrowDownLeft,
  p2p_out: ArrowUpRight,
  atm: Banknote,
};

interface KeyTransactionsListProps {
  transactions: KeyTransaction[];
}

export function KeyTransactionsList({ transactions }: KeyTransactionsListProps) {
  return (
    <Card
      title="Key Transactions"
      subtitle="The customer's largest transactions on file"
    >
      <ul className="divide-y divide-line/60">
        {transactions.map((txn) => {
          const Icon = ICONS[txn.category] ?? ReceiptText;
          const credit = txn.amount >= 0;
          return (
            <li key={txn.id} className="flex items-center gap-3 py-3">
              <div
                className={`flex size-9 shrink-0 items-center justify-center rounded-full ${
                  credit ? "bg-mint text-forest" : "bg-sage text-ink-soft"
                }`}
              >
                <Icon size={16} strokeWidth={1.8} />
              </div>
              <div className="min-w-0 flex-1 leading-tight">
                <div className="truncate text-sm font-medium">{txn.label}</div>
                <div className="font-mono text-xs text-ink-muted">{txn.meta}</div>
              </div>
              <span
                className={`shrink-0 text-sm font-semibold ${
                  credit ? "text-emerald" : "text-negative"
                }`}
              >
                {credit ? "+" : "−"}
                {inr(Math.abs(txn.amount))}
              </span>
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

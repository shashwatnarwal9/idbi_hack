/**
 * Shared data contracts for the आय·AI dashboard.
 * Shapes mirror the Postgres serving store (customer_profiles,
 * prospect_scores, spending_breakdown), so mock data can be swapped for a
 * real API without touching components.
 */

export type IncomeType = "salaried" | "gig" | "business";
export type RiskCapacity = "low" | "medium" | "high";
export type ConfidenceBand = "high" | "medium" | "low";

export interface CustomerProfile {
  customerId: string;
  region: string;
  incomeType: IncomeType;
  trueMonthlyIncome: number;
  declaredMonthlyIncome: number;
  incomeVolatility: number;
  avgMonthlyEssentials: number;
  totalEmi: number;
  totalSip: number;
  investableSurplus: number;
  surplusStability: number;
  savingsRate: number;
  riskCapacity: RiskCapacity;
  monthsHistory: number;
  pctCategorized: number;
  occupationDeclared: string;
  confidenceBand: ConfidenceBand;
}

export interface ReasonCode {
  feature: string;
  value: number;
  shap: number;
}

export interface ProspectScore {
  customerId: string;
  pGoodProspect: number;
  reasons: ReasonCode[];
}

export interface SpendingSlice {
  category: string;
  avgMonthly: number;
}

/** One point of the reconstructed-vs-declared income series. */
export interface MonthlyIncomePoint {
  month: string;
  reconstructed: number;
  declared: number;
}

export interface IncomeCallout {
  month: string;
  label: string;
}

export interface ReasonChip {
  /** Gold feature name, rendered in monospace. */
  feature: string;
  direction: "up" | "down";
}

export interface RecentProspect {
  customerId: string;
  name: string;
  reviewed: boolean;
  /** Prospect score scaled to 0-100. */
  score: number;
  band: ConfidenceBand;
  reasons: ReasonChip[];
}

export interface ConfidenceSlice {
  band: ConfidenceBand;
  count: number;
}

/** One reconstructed income stream with its detected pattern. */
export interface IncomeStream {
  label: string;
  sharePct: number;
  note: string;
}

/** Signed money line for the surplus waterfall (income +, outflows -). */
export interface SurplusLine {
  label: string;
  amount: number;
}

export interface KeyTransaction {
  id: string;
  label: string;
  meta: string;
  /** Signed: credits positive, debits negative. */
  amount: number;
  /** Silver category; drives the row icon. */
  category: string;
}

/** SHAP driver expressed in score points (positive or negative). */
export interface ScoreDriver {
  label: string;
  points: number;
}

export type GateStatus = "passed" | "warning" | "notrun";
export type CheckStatus = "pass" | "warn" | "fail";

export interface GateCheck {
  label: string;
  status: CheckStatus;
  note?: string;
}

export interface GateCardData {
  layer: string;
  /** What kind of checks these are, e.g. "GE gate suite" or "structural checks". */
  kind: string;
  status: GateStatus;
  /** Share of checks passed in the last run, [0, 1]. */
  quality: number;
  qualityDetail: string;
  checks: GateCheck[];
}

/** Confidence band counts within one months-of-history bucket. */
export interface HistoryBucket {
  bucket: string;
  high: number;
  medium: number;
  low: number;
}

export interface ValidationLogRow {
  timestamp: string;
  /** GE suite the expectation ran in, e.g. "gold_gate". */
  layer: string;
  expectation: string;
  status: "PASS" | "FAIL";
  impact: string;
}

export interface CustomerDetail {
  customerId: string;
  name: string;
  memberSince: string;
  location: string;
  occupation: string;
  declaredMonthly: number;
  reconstructedMonthly: number;
  score: number;
  scoreLabel: string;
  band: ConfidenceBand;
  monthsHistory: number;
  parseQuality: number;
  incomeStreams: IncomeStream[];
  surplusLines: SurplusLine[];
  surplus: number;
  savingsNote: string;
  transactions: KeyTransaction[];
  positiveDrivers: ScoreDriver[];
  negativeDrivers: ScoreDriver[];
  reasoning: string;
}

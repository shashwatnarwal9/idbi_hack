/** Response shapes of the aayai API — the only source of rendered values. */

import type { ConfidenceBand } from "../mocks/types";

export interface ReasonCode {
  feature: string;
  value: number;
  shap: number;
}

export interface RankedCustomer {
  rank: number;
  customer_id: string;
  name: string;
  score: number;
  band: ConfidenceBand;
  reasons: ReasonCode[];
  reviewed: boolean;
}

export interface OverviewSummary {
  customers: number;
  avg_reconstructed: number | null;
  avg_declared: number | null;
  median_surplus: number | null;
  bands: { high: number; medium: number; low: number };
  income_by_month: { month: string; avg_income: number }[];
}

export interface ReviewState {
  reviewed: boolean;
  reviewed_at: string | null;
  reviewed_by: string | null;
}

export interface ShareRecord {
  shared_at: string;
  shared_by: string | null;
  document_type: string;
}

export interface CustomerProfileApi {
  customer_id: string;
  name: string;
  account_open_date: string | null;
  region: string | null;
  income_type: string;
  true_monthly_income: number;
  income_volatility: number;
  avg_monthly_essentials: number;
  total_emi: number;
  total_sip: number;
  investable_surplus: number;
  surplus_stability: number;
  savings_rate: number;
  risk_capacity: string;
  months_history: number;
  pct_categorized: number;
  occupation_declared: string | null;
  declared_monthly_income: number | null;
  confidence_band: ConfidenceBand;
}

export interface IncomeStreamApi {
  category: string;
  avg_monthly: number;
  share: number;
  months_seen: number;
}

export interface KeyTransactionApi {
  txn_id: string;
  date: string;
  label: string;
  channel: string;
  category: string;
  direction: string;
  amount: number;
}

export interface LoanEligibility {
  product: string;
  label: string;
  status: "eligible" | "not_eligible";
  reason: string | null;
  suggested_amount: number | null;
}

export interface LoanAssessmentRow {
  customer_id: string;
  name: string;
  source: string;
  score: number;
  confidence_band: ConfidenceBand;
  reviewed: boolean;
  status: "eligible" | "not_eligible";
  reason: string | null;
  suggested_amount: number | null;
}

export interface LoanAssessmentSummary {
  customers: number;
  products: {
    product: string;
    label: string;
    eligible: number;
    not_eligible: number;
  }[];
}

/** GET /customers/{id}/loan-calc — one product evaluated at given terms. */
export interface LoanCalcResponse {
  customer_id: string;
  name: string;
  confidence_band: ConfidenceBand;
  product: string;
  label: string;
  terms: { annual_rate_pct: number; tenure_months: number };
  base_eligibility: LoanEligibility;
  affordability: {
    affordable_emi: number;
    binding_cap: "surplus" | "foir" | null;
    max_loan_amount: number;
    current_dti: number | null;
  };
  requested: {
    amount: number;
    emi: number;
    post_loan_dti: number | null;
    total_repayment: number;
    total_interest: number;
    status: "eligible" | "not_eligible";
    reasons: string[];
  } | null;
  disclaimer: string;
}

export interface CustomerAnalysis {
  profile: CustomerProfileApi;
  score: { p_good_prospect: number; reasons: ReasonCode[] } | null;
  surplus_breakdown: {
    income: number;
    essentials: number;
    emis: number;
    buffer: number;
    surplus: number;
  };
  income_streams: IncomeStreamApi[];
  key_transactions: KeyTransactionApi[];
  review: ReviewState | null;
  last_share?: ShareRecord | null;
  loan_eligibility: LoanEligibility[];
}

export interface SearchResult {
  customer_id: string;
  name: string;
  band: ConfidenceBand;
  reviewed: boolean;
}

export interface PipelineTask {
  task_id: string;
  state: string | null;
  start_date: string | null;
  end_date: string | null;
  duration: number | null;
}

export interface LocalSetup {
  repo_url: string;
  repo_dir: string;
  clone: string;
  cd: string;
  up: string;
  airflow_url: string;
}

export interface PipelineState {
  available: boolean;
  reason?: string;
  ui_url: string;
  setup?: LocalSetup;
  run: {
    run_id: string;
    state: string;
    start_date: string | null;
    end_date: string | null;
  } | null;
  tasks: PipelineTask[];
}

export interface GateSuiteResult {
  suite: string;
  passed: boolean;
  checks: number;
  failed: string[];
}

export interface GateResult {
  passed: boolean;
  suites: GateSuiteResult[];
}

export interface HistoryEntry {
  customer_id: string;
  months: number;
  active_months: number;
}

export interface AnalyzeResult {
  batch_id: string;
  customers: number;
  transactions_used: number;
  issues: string[];
  status: string;
  gates: GateResult | null;
  history: HistoryEntry[];
  min_history_months: number | null;
}

export interface MergeResult {
  batch_id: string;
  merged?: number;
  skipped_duplicates?: number;
  removed?: number;
  status: string;
}

export interface BatchSummary {
  customers: number;
  avg_reconstructed: number | null;
  median_surplus: number | null;
  bands: { high: number; medium: number; low: number };
  high_prospects: number;
}

/** One row of the "Past Batches" list — computed results only, isolated from
 * the operational book until an explicit merge. */
export type BatchPhase =
  | "isolated_preview"
  | "validated_merged"
  | "failed_gate"
  | "reverted";

export interface ValidationFailure {
  expectation_name: string;
  layer: string;
  detail: string;
  severity: string;
}

export interface ValidationCheck {
  expectation: string;
  detail: string;
}

export interface ValidationSuite {
  suite: string;
  layer: string;
  role: "gate" | "feature";
  purpose: string;
  checks: ValidationCheck[];
  n_expectations: number;
}

export interface ValidationStructure {
  suites: ValidationSuite[];
  totals: {
    suites: number;
    gates: number;
    expectations: number;
    gate_expectations: number;
  };
  bands: { high: number; medium: number; low: number };
  customers: number;
  firewall: string;
}

export interface UploadBatch {
  batch_id: string;
  created_at: string;
  n_customers: number;
  n_transactions: number;
  note: string | null;
  name: string;
  uploaded_by: string | null;
  status: string;
  phase: BatchPhase;
  gates: GateResult | null;
  failure_reasons: ValidationFailure[];
  min_history_months: number | null;
  merged_at: string | null;
}

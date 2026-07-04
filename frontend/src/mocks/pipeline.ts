import type { GateCardData, HistoryBucket, ValidationLogRow } from "./types";

/**
 * Results of the latest batch validation run (2 Jul 2026). Every expectation
 * name, count and status below mirrors the actual Great Expectations suites in
 * src/aayai/validation/run.py — nothing is invented.
 */
export const lastRun = {
  timestamp: "2 Jul 2026, 20:12 IST",
  expectationsEvaluated: 28, // silver_gate 11 + gold_gate 13 + gold_confidence 4
};

export const gateCards: GateCardData[] = [
  {
    layer: "Bronze",
    kind: "Structural checks (pre-GE)",
    status: "passed",
    quality: 1,
    qualityDetail: "3 of 3 checks passed",
    checks: [
      { label: "Row parity with raw CSVs (84,818 / 200)", status: "pass" },
      { label: "Typed schema on read-back (timestamp, amounts)", status: "pass" },
      { label: "Partition layout year=YYYY/month=MM (18 partitions)", status: "pass" },
    ],
  },
  {
    layer: "Silver",
    kind: "GE gate suite: silver_gate",
    status: "passed",
    quality: 1,
    qualityDetail: "11 of 11 expectations passed",
    checks: [
      { label: "Null checks on 7 key columns", status: "pass" },
      { label: "Ranges: amount > 0, parse_confidence in [0, 1]", status: "pass" },
      { label: "Domains: direction, 16-category taxonomy", status: "pass" },
    ],
  },
  {
    layer: "Gold",
    kind: "GE suites: gold_gate + gold_confidence",
    status: "warning",
    quality: 15 / 17,
    qualityDetail: "15 of 17 expectations passed (2 trust tiers flagged)",
    checks: [
      { label: "Key-field nulls and customer_id uniqueness", status: "pass" },
      { label: "Business ranges: income, surplus, history, coverage", status: "pass" },
      {
        label: "Trust tier thresholds (coverage ≥ 0.90 / ≥ 0.85)",
        status: "warn",
        note: "27 customers below the high tier, 2 below medium",
      },
    ],
  },
];

/**
 * Confidence bands by months-of-history bucket. The synthetic cohort all has
 * exactly 18 months of history, so one bucket carries the whole book.
 */
export const historyBuckets: HistoryBucket[] = [
  { bucket: "New user", high: 0, medium: 0, low: 0 },
  { bucket: "6-12 mo", high: 0, medium: 0, low: 0 },
  { bucket: "12-18 mo", high: 0, medium: 0, low: 0 },
  { bucket: "18-24 mo", high: 173, medium: 25, low: 2 },
  { bucket: "24 mo+", high: 0, medium: 0, low: 0 },
];

export const validationLog: ValidationLogRow[] = [
  {
    timestamp: "2026-07-02 20:12:01",
    layer: "silver_gate",
    expectation: "expect_column_values_to_not_be_null(txn_id)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:01",
    layer: "silver_gate",
    expectation: "expect_column_values_to_be_between(parse_confidence, 0, 1)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:02",
    layer: "silver_gate",
    expectation: "expect_column_values_to_be_in_set(category)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:03",
    layer: "gold_gate",
    expectation: "expect_column_values_to_be_unique(customer_id)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:03",
    layer: "gold_gate",
    expectation: "expect_column_values_to_be_between(true_monthly_income, min=0)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:03",
    layer: "gold_gate",
    expectation: "expect_column_values_to_be_between(investable_surplus)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:04",
    layer: "gold_confidence",
    expectation: "expect_column_values_to_be_between(months_history, min=12)",
    status: "PASS",
    impact: "—",
  },
  {
    timestamp: "2026-07-02 20:12:04",
    layer: "gold_confidence",
    expectation: "expect_column_values_to_be_between(pct_categorized, min=0.90)",
    status: "FAIL",
    impact: "27 customers demoted to medium band",
  },
  {
    timestamp: "2026-07-02 20:12:04",
    layer: "gold_confidence",
    expectation: "expect_column_values_to_be_between(pct_categorized, min=0.85)",
    status: "FAIL",
    impact: "2 customers assigned low band",
  },
];

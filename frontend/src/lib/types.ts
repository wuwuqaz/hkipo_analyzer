export type JobStatus = "queued" | "running" | "success" | "failed" | "not_found";

export type JobResponse = {
  job_id: string;
  status: JobStatus;
  created_at: string;
};

export type JobStatusResponse = {
  job_id: string;
  status: JobStatus;
  stock_code: string | null;
  company_name: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type AnalyzeResultResponse = {
  job_id: string;
  stock_code: string | null;
  company_name: string | null;
  result: Record<string, unknown>;
};

export type ReanalyzeRequest = {
  stock_code: string;
  company_name?: string;
  historical_market_data?: Record<string, unknown>;
};

export type JobsListResponse = {
  jobs: JobStatusResponse[];
  total: number;
};

export type LiveResultsResponse = {
  results: Record<string, unknown>[];
  cache_time: string | null;
  total: number;
};

export type LiveStatusResponse = {
  has_running_job: boolean;
  latest_job_id: string | null;
  latest_job_status: string | null;
};

export type HistoryRecord = {
  stock_code: string;
  company_name: string;
  trade_score: number;
  strict_ipo_score: number;
  raw_trade_signal_score: number;
  long_term_score: number;
  subscription_recommendation: string;
  valuation_pressure: string;
  market_heat: string;
  apply_end_date: string;
  tracking_status: string;
  has_post_listing: boolean;
  score: number;
  _raw: Record<string, unknown>;
};

export type HistoryListResponse = {
  records: HistoryRecord[];
  total: number;
};

export type BloggerConsensusResponse = {
  stock_code: string;
  consensus_score: number | null;
  total_posts: number;
  positive_count: number;
  neutral_count: number;
  negative_count: number;
  sentiment_label: string | null;
  top_reasons: string[];
  top_risks: string[];
  representative_posts: { title: string; url: string; sentiment: string }[];
  message: string | null;
};

export type PeerRecord = {
  name: string;
  ticker: string;
  type: string;
  sector: string;
  subsector: string;
  ps: number | null;
  pe: number | null;
  market_cap_hkd_million: number | null;
  revenue_growth_pct: number | null;
  gross_margin_pct: number | null;
  is_stale: boolean;
  data_quality: string;
};

export type PeerListResponse = {
  peers: PeerRecord[];
  total: number;
  sectors: string[];
  subsectors: string[];
};

/* ------------------------------------------------------------------ */
/* AnalysisResult — IPO 分析结果统一类型                               */
/* ------------------------------------------------------------------ */

export interface CompanyProfile {
  company_summary: string;
  industry: string;
  main_business: string;
  market_position: string;
  key_products: string[];
  geographic_focus: string;
  founded_year: number | null;
  headquarters: string;
  business_model: string;
  customer_type: string;
  customer_industries: string;
  revenue_scale: string;
  confidence: string;
}

export interface CornerstoneInvestor {
  name: string;
  commitment_hkd_million?: number;
  type?: string;
}

export interface CornerstoneAnalysis {
  score: number;
  investors: CornerstoneInvestor[];
  lockup_period_months?: number;
  total_commitment_pct?: number;
}

export interface StockQuality {
  score: number;
  label: string;
  dimensions: Record<string, { label: string; detail: string }>;
  reasons: string[];
}

export interface ProspectusInfo {
  sector: string;
  offer_price: number;
  lot_size: number;
  market_cap_hkd_million: number;
  apply_end_date?: string;
  company_profile?: CompanyProfile;
  cornerstone_analysis?: CornerstoneAnalysis;
  stock_quality?: StockQuality;
  investment_thesis?: Record<string, unknown>;
}

export interface InvestmentThesis {
  overall_tone: string;
  one_line_conclusion: string;
  conclusion?: string;
  fundamental_diagnosis: unknown[];
  business_model_takeaways: unknown[];
  valuation_takeaways: unknown[];
  catalysts: unknown[];
  invalidation_signals: unknown[];
  missing_angles: unknown[];
  short_seller_case?: Record<string, unknown>;
}

export interface ScoreBreakdownItem {
  score: number;
  max_score: number;
  normalized_score?: number;
  detail: string;
}

export interface AnalysisResult {
  hk_code: string;
  stock_code: string;
  company_name: string;
  score: number;
  trade_score: number;
  strict_ipo_score?: number;
  ipo_trade_score?: number;
  long_term_score: number;
  raw_long_term_score_before_penalty?: number;
  long_term_penalty?: number;
  long_term_penalty_reasons?: string[];
  strict_cap_reasons?: string[];
  valuation_score: number;
  fundamental_score: number;
  theme_score?: number;
  valuation_pressure_label: string;
  market_heat: string;
  over_sub_ratio?: number;
  subscription_recommendation: string;
  ipo_trade_label?: string;
  long_term_label?: string;
  apply_start_date?: string;
  apply_end_date?: string;
  margin_total_hkd_billion?: number;
  margin_total?: number;
  margin_detail?: Record<string, unknown>;
  risk_penalty?: number;
  financial_data_quality_flags?: string[];
  financial_extract_confidence?: string;
  score_breakdown?: Record<string, ScoreBreakdownItem>;
  prospectus_info?: ProspectusInfo;
  stock_quality?: StockQuality;
  investment_thesis?: InvestmentThesis;

  /* 后端原始字段（历史记录中使用） */
  offer_price?: number;
  market_cap_hkd_million?: number;
  lot_size?: number;
  board_lot?: number;
  public_offer_lots?: number;
  hk_offer_shares?: number;
}

/* ------------------------------------------------------------------ */
/* Backtest — IPO 首日表现回测                                         */
/* ------------------------------------------------------------------ */

export type BacktestGroupStats = {
  count: number;
  win_rate: number;
  median_return: number;
  mean_return: number;
  big_meat_50_rate: number;
  break_rate: number;
};

export type BacktestRecordItem = {
  hk_code: string;
  stock_code: string;
  company_name: string;
  listing_date: string;
  offer_price: number | null;
  first_day_open: number | null;
  first_day_close: number | null;
  first_day_high: number | null;
  first_day_low: number | null;
  first_day_return: number;
  is_break: boolean;
  is_big_meat_50: boolean;
  over_sub_ratio: number;
  has_greenshoe: boolean | null;
  cornerstone_pct: number | null;
  cornerstone_independence: string | null;
  has_related_support: boolean;
  fundamental_score: number | null;
  sponsor_elastic_group: string | null;
  subscription_heat_group: string | null;
  one_lot_success_rate: number | null;
  clawback_ratio: number | null;
  market_wind_score: number | null;
  market_wind_group: string | null;
  bottom_group: string | null;
  wind_group: string | null;
  sponsors: string[];
  cornerstone_investors: string[];
};

export type IpoFirstDayBacktestResponse = {
  total: BacktestGroupStats;
  greenshoe: Record<string, BacktestGroupStats>;
  sponsor_elastic: Record<string, BacktestGroupStats>;
  cornerstone_pct: Record<string, BacktestGroupStats>;
  cornerstone_independence: Record<string, BacktestGroupStats>;
  subscription_heat: Record<string, BacktestGroupStats>;
  market_wind: Record<string, BacktestGroupStats>;
  bottom_x_wind: Record<string, BacktestGroupStats>;
  records: BacktestRecordItem[];
  run_at: string;
};

export type BacktestStatusResponse = {
  sample_count: number;
  ready: boolean;
  message: string;
};

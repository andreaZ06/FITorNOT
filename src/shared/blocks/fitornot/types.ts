export type FitOrNotIntentSlots = {
  category: string;
  brand?: string | null;
  model?: string | null;
  urls: string[];
};

export type FitOrNotRetrievalPlan = {
  ecommerce_query: string;
  xiaohongshu_queries: string[];
};

export type FitOrNotEvidenceItem = {
  source: string;
  text: string;
  platform?: string | null;
  url?: string | null;
};

export type FitOrNotRawData = {
  retrieval_plan: FitOrNotRetrievalPlan;
  verified_specs: Record<string, unknown>;
  ecommerce_evidence: FitOrNotEvidenceItem[];
  xiaohongshu_evidence: FitOrNotEvidenceItem[];
  blocked_sources: Array<Record<string, string>>;
};

export type FitOrNotRiskFinding = {
  issue: string;
  evidence: string;
  source: string;
};

export type FitOrNotCleanedFindings = {
  core_scandals: FitOrNotRiskFinding[];
  soft_drawbacks: FitOrNotRiskFinding[];
  noise_rate: Record<string, string>;
};

export type FitOrNotScenarioFit = {
  user_profile_extracted: string;
  marketing_clash?: string | null;
  suitability_analysis: string;
};

export type FitOrNotDecisionResponse = {
  slots: FitOrNotIntentSlots;
  retrieval_plan: FitOrNotRetrievalPlan;
  raw_data: FitOrNotRawData;
  cleaned_findings: FitOrNotCleanedFindings;
  scenario_fit: FitOrNotScenarioFit;
  ecommerce_data: Array<Record<string, unknown>>;
  xiaohongshu_data: Array<Record<string, unknown>>;
  social_data: Array<Record<string, unknown>>;
  blocked_sources: Array<Record<string, string>>;
  report: string;
};

export type FitOrNotVerdictTone = 'veto' | 'caution' | 'fit' | 'unknown';

export type FitOrNotHistoryEntry = {
  id: string;
  createdAt: string;
  userRawInput: string;
  targetLanguage: string;
  summaryTitle: string;
  verdictTone: FitOrNotVerdictTone;
  response: FitOrNotDecisionResponse;
};

export type FitOrNotPendingRequest = {
  id: string;
  userRawInput: string;
  targetLanguage: string;
};

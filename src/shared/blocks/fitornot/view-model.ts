import type {
  FitOrNotDecisionResponse,
  FitOrNotHistoryEntry,
  FitOrNotVerdictTone,
} from './types';

function truncateText(value: string, maxLength = 48) {
  if (value.length <= maxLength) {
    return value;
  }

  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
}

function hasUsableEvidence(response: FitOrNotDecisionResponse) {
  return (
    response.cleaned_findings.core_scandals.length > 0 ||
    response.cleaned_findings.soft_drawbacks.length > 0 ||
    response.raw_data.ecommerce_evidence.length > 0 ||
    response.raw_data.xiaohongshu_evidence.length > 0 ||
    response.ecommerce_data.length > 0 ||
    response.xiaohongshu_data.length > 0 ||
    response.social_data.length > 0
  );
}

export function getFitOrNotVerdictTone(
  response: FitOrNotDecisionResponse
): FitOrNotVerdictTone {
  const blockedSourcesCount =
    response.blocked_sources.length + response.raw_data.blocked_sources.length;

  if (blockedSourcesCount > 0 && !hasUsableEvidence(response)) {
    return 'unknown';
  }

  if (response.cleaned_findings.core_scandals.length > 0) {
    return 'veto';
  }

  if (response.cleaned_findings.soft_drawbacks.length > 0) {
    return 'caution';
  }

  return 'fit';
}

export function getFitOrNotSummaryTitle(
  response: FitOrNotDecisionResponse,
  fallbackRawInput: string
) {
  const brand = response.slots.brand?.trim();
  const model = response.slots.model?.trim();

  if (brand && model) {
    return `${brand} ${model}`;
  }

  if (brand) {
    return brand;
  }

  if (model) {
    return model;
  }

  return truncateText(fallbackRawInput.trim());
}

export function buildFitOrNotHistoryEntry(params: {
  id: string;
  userRawInput: string;
  targetLanguage: string;
  response: FitOrNotDecisionResponse;
}): FitOrNotHistoryEntry {
  const { id, response, targetLanguage, userRawInput } = params;

  return {
    id,
    createdAt: new Date().toISOString(),
    userRawInput,
    targetLanguage,
    summaryTitle: getFitOrNotSummaryTitle(response, userRawInput),
    verdictTone: getFitOrNotVerdictTone(response),
    response,
  };
}

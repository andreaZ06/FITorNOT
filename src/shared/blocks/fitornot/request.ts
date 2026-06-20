import type { FitOrNotDecisionResponse } from './types';

type FitOrNotDecisionRouteResponse = {
  code?: number;
  message?: string;
  data?: FitOrNotDecisionResponse;
};

type FitOrNotDecisionRequest = {
  userRawInput: string;
  targetLanguage: string;
  apiBaseUrl?: string | null;
};

function isTransportLevelFetchError(error: unknown) {
  if (!(error instanceof Error)) {
    return false;
  }

  const normalizedMessage = error.message.trim().toLowerCase();
  return (
    normalizedMessage === 'failed to fetch' ||
    normalizedMessage.includes('networkerror') ||
    normalizedMessage.includes('load failed')
  );
}

function normalizeApiBaseUrl(value?: string | null): string | null {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }

  return trimmed.replace(/\/+$/, '');
}

function summarizeTextResponse(value: string): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return 'empty response body';
  }

  if (normalized.includes('FUNCTION_INVOCATION_TIMEOUT')) {
    return `FUNCTION_INVOCATION_TIMEOUT: ${normalized}`;
  }

  return normalized.slice(0, 240);
}

async function readJsonOrText<T>(response: Response): Promise<{
  json?: T;
  text?: string;
}> {
  const rawText = await response.text();
  const text = rawText.trim();

  if (!text) {
    return {};
  }

  try {
    return {
      json: JSON.parse(text) as T,
    };
  } catch {
    return {
      text,
    };
  }
}

async function requestViaProxy({
  userRawInput,
  targetLanguage,
}: FitOrNotDecisionRequest): Promise<FitOrNotDecisionResponse> {
  const response = await fetch('/api/fitornot/decision', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      userRawInput,
      targetLanguage,
    }),
  });

  const payload = await readJsonOrText<FitOrNotDecisionRouteResponse>(response);
  if (!payload.json) {
    throw new Error(summarizeTextResponse(payload.text || response.statusText));
  }

  if (!response.ok || payload.json.code !== 0 || !payload.json.data) {
    throw new Error(payload.json.message || 'FITorNOT request failed');
  }

  return payload.json.data;
}

async function requestDirect({
  userRawInput,
  targetLanguage,
  apiBaseUrl,
}: FitOrNotDecisionRequest): Promise<FitOrNotDecisionResponse> {
  const normalizedBaseUrl = normalizeApiBaseUrl(apiBaseUrl);
  if (!normalizedBaseUrl) {
    throw new Error('FITorNOT backend base URL is missing');
  }

  const response = await fetch(`${normalizedBaseUrl}/api/v1/decision`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      user_raw_input: userRawInput,
      target_language: targetLanguage,
    }),
  });

  const payload = await readJsonOrText<FitOrNotDecisionResponse & { detail?: string; message?: string }>(response);
  if (!payload.json) {
    throw new Error(summarizeTextResponse(payload.text || response.statusText));
  }

  if (!response.ok) {
    throw new Error(payload.json.detail || payload.json.message || response.statusText || 'FITorNOT backend request failed');
  }

  return payload.json;
}

export async function requestFitOrNotDecision(
  payload: FitOrNotDecisionRequest
): Promise<FitOrNotDecisionResponse> {
  const normalizedBaseUrl = normalizeApiBaseUrl(payload.apiBaseUrl);
  if (normalizedBaseUrl) {
    try {
      return await requestDirect({
        ...payload,
        apiBaseUrl: normalizedBaseUrl,
      });
    } catch (error) {
      if (!isTransportLevelFetchError(error)) {
        throw error;
      }

      return requestViaProxy(payload);
    }
  }

  return requestViaProxy(payload);
}

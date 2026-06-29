import { envConfigs } from '@/config';
import { respData, respErr } from '@/shared/lib/resp';

export const maxDuration = 300;

type FitOrNotDecisionRequest = {
  userRawInput?: string;
  targetLanguage?: string;
};

function isLocalHostname(hostname: string) {
  const normalizedHostname = hostname.trim().toLowerCase();
  return (
    normalizedHostname === '127.0.0.1' ||
    normalizedHostname === 'localhost' ||
    normalizedHostname === '0.0.0.0' ||
    normalizedHostname === '::1'
  );
}

function resolveFitOrNotBackendBaseUrl() {
  const configuredBaseUrl =
    process.env.FITORNOT_API_BASE_URL?.trim() ||
    envConfigs.fitornot_api_base_url?.trim() ||
    'http://127.0.0.1:8000';

  let parsedUrl: URL;
  try {
    parsedUrl = new URL(configuredBaseUrl);
  } catch {
    throw new Error(
      `FITORNOT_API_BASE_URL is invalid: ${configuredBaseUrl}. Please provide a full http(s) origin.`
    );
  }

  if (process.env.NODE_ENV === 'production' && isLocalHostname(parsedUrl.hostname)) {
    throw new Error(
      `FITORNOT_API_BASE_URL is pointing to localhost (${parsedUrl.origin}). Deploy the review-pitfall-checker-v2 backend to a public https URL and set FITORNOT_API_BASE_URL in Vercel before retrying.`
    );
  }

  return parsedUrl.origin;
}

async function readUpstreamError(response: Response) {
  const text = (await response.text()).trim();
  if (!text) {
    return response.statusText || 'unknown upstream error';
  }

  try {
    const payload = JSON.parse(text);
    if (typeof payload?.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (typeof payload?.message === 'string' && payload.message.trim()) {
      return payload.message.trim();
    }
  } catch {
    return text.replace(/\s+/g, ' ').trim().slice(0, 240);
  }

  return response.statusText || text.replace(/\s+/g, ' ').trim().slice(0, 240);
}

async function readUpstreamPayload(response: Response) {
  const text = (await response.text()).trim();
  if (!text) {
    return { payload: null, rawText: '' };
  }

  try {
    return {
      payload: JSON.parse(text),
      rawText: text,
    };
  } catch {
    return {
      payload: null,
      rawText: text,
    };
  }
}

export async function POST(request: Request) {
  try {
    const { userRawInput, targetLanguage } =
      (await request.json()) as FitOrNotDecisionRequest;

    if (!userRawInput?.trim() || !targetLanguage?.trim()) {
      return respErr('invalid params');
    }

    const baseUrl = resolveFitOrNotBackendBaseUrl();
    const response = await fetch(`${baseUrl}/api/v1/decision`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        user_raw_input: userRawInput.trim(),
        target_language: targetLanguage.trim(),
      }),
    });

    if (!response.ok) {
      const errorMessage = await readUpstreamError(response);
      return respErr(
        `FITorNOT backend request failed with status ${response.status}: ${errorMessage}`
      );
    }

    const { payload, rawText } = await readUpstreamPayload(response);
    if (!payload) {
      return respErr(
        `FITorNOT backend returned a non-JSON response: ${rawText
          .replace(/\s+/g, ' ')
          .trim()
          .slice(0, 240)}`
      );
    }

    return respData(payload);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'fitornot decision failed';
    return respErr(message);
  }
}

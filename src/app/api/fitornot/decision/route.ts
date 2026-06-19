import { envConfigs } from '@/config';
import { respData, respErr } from '@/shared/lib/resp';

type FitOrNotDecisionRequest = {
  userRawInput?: string;
  targetLanguage?: string;
};

async function readUpstreamError(response: Response) {
  try {
    const payload = await response.json();
    if (typeof payload?.detail === 'string' && payload.detail.trim()) {
      return payload.detail.trim();
    }
    if (typeof payload?.message === 'string' && payload.message.trim()) {
      return payload.message.trim();
    }
  } catch {
    // Ignore JSON parsing errors and fall back to status text.
  }

  return response.statusText || 'unknown upstream error';
}

export async function POST(request: Request) {
  try {
    const { userRawInput, targetLanguage } =
      (await request.json()) as FitOrNotDecisionRequest;

    if (!userRawInput?.trim() || !targetLanguage?.trim()) {
      return respErr('invalid params');
    }

    const baseUrl =
      envConfigs.fitornot_api_base_url ||
      process.env.FITORNOT_API_BASE_URL ||
      'http://127.0.0.1:8000';
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

    const payload = await response.json();

    return respData(payload);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : 'fitornot decision failed';
    return respErr(message);
  }
}

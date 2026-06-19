import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

describe('POST /api/fitornot/decision in production', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.restoreAllMocks();
    vi.stubEnv('NODE_ENV', 'production');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    delete process.env.FITORNOT_API_BASE_URL;
  });

  it('returns an actionable error when the production backend URL still points to localhost', async () => {
    process.env.FITORNOT_API_BASE_URL = 'http://127.0.0.1:8000';

    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);

    const { POST } = await import('@/app/api/fitornot/decision/route');

    const response = await POST(
      new Request('http://localhost/api/fitornot/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          userRawInput: 'anker 10000',
          targetLanguage: 'zh-CN',
        }),
      })
    );
    const payload = await response.json();

    expect(fetchMock).not.toHaveBeenCalled();
    expect(payload.code).toBe(-1);
    expect(payload.message).toContain('FITORNOT_API_BASE_URL');
    expect(payload.message).toContain('localhost');
  });
});

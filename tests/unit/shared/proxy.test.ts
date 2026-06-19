import { beforeEach, describe, expect, it, vi } from 'vitest';
import { NextRequest, NextResponse } from 'next/server';

const { intlMiddlewareMock, getSessionCookieMock } = vi.hoisted(() => ({
  intlMiddlewareMock: vi.fn(),
  getSessionCookieMock: vi.fn(),
}));

vi.mock('next-intl/middleware', () => ({
  default: vi.fn(() => intlMiddlewareMock),
}));

vi.mock('better-auth/cookies', () => ({
  getSessionCookie: getSessionCookieMock,
}));

import { proxy } from '@/proxy';

describe('proxy', () => {
  beforeEach(() => {
    intlMiddlewareMock.mockReset();
    getSessionCookieMock.mockReset();
  });

  it('normalizes self-redirecting default-locale responses into rewrites', async () => {
    intlMiddlewareMock.mockImplementation((request: NextRequest) => {
      const response = NextResponse.redirect(request.nextUrl.href);
      response.headers.set(
        'x-middleware-rewrite',
        'http://localhost:3000/en/fitornot'
      );
      return response;
    });

    const request = new NextRequest('http://localhost:3000/fitornot');
    const response = await proxy(request);

    expect(response.headers.get('location')).toBeNull();
    expect(response.headers.get('x-middleware-rewrite')).toBe(
      'http://localhost:3000/en/fitornot'
    );
    expect(response.status).toBe(200);
  });
});

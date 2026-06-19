import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const repoRoot = process.cwd();

describe('FITorNOT dev launcher', () => {
  it('exposes a package script for starting the full local FITorNOT stack', () => {
    const packageJson = JSON.parse(
      readFileSync(join(repoRoot, 'package.json'), 'utf8')
    ) as { scripts: Record<string, string> };

    expect(packageJson.scripts['dev:fitornot']).toBe(
      'powershell -ExecutionPolicy Bypass -File scripts/start-fitornot-dev.ps1'
    );
  });

  it('starts the FastAPI backend and Next frontend with the expected local ports', () => {
    const script = readFileSync(
      join(repoRoot, 'scripts/start-fitornot-dev.ps1'),
      'utf8'
    );

    expect(script).toContain('review-pitfall-checker-v2');
    expect(script).toContain('FITORNOT_API_BASE_URL');
    expect(script).toContain('DEEPSEEK_API_KEY');
    expect(script).toContain('uvicorn');
    expect(script).toContain('main:app');
    expect(script).toMatch(/"--port"[\s\S]*"\$BackendPort"/);
    expect(script).toMatch(/"--port"[\s\S]*"\$FrontendPort"/);
  });
});

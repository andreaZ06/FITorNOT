import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const repoRoot = process.cwd();

describe('next-mdx-remote dependency policy', () => {
  it('pins next-mdx-remote to a non-vulnerable major version', () => {
    const packageJson = JSON.parse(
      readFileSync(join(repoRoot, 'package.json'), 'utf8')
    ) as { dependencies?: Record<string, string> };

    const declaredVersion = packageJson.dependencies?.['next-mdx-remote'];

    expect(declaredVersion).toBeTruthy();

    const majorVersion = Number.parseInt(
      declaredVersion!.replace(/^[^\d]*/, '').split('.')[0] ?? '',
      10
    );

    expect(majorVersion).toBeGreaterThanOrEqual(6);
  });
});

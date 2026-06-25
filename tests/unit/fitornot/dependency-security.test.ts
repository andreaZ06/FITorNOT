import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

type DependencyMap = Record<string, string>;

function parseVersion(version: string): [number, number, number] {
  const match = version.match(/(\d+)\.(\d+)\.(\d+)/);

  if (!match) {
    throw new Error(`Unable to parse semver from "${version}"`);
  }

  return [
    Number.parseInt(match[1], 10),
    Number.parseInt(match[2], 10),
    Number.parseInt(match[3], 10),
  ];
}

function isVersionAtLeast(version: string, minimum: string): boolean {
  const currentParts = parseVersion(version);
  const minimumParts = parseVersion(minimum);

  for (let index = 0; index < currentParts.length; index += 1) {
    if (currentParts[index] > minimumParts[index]) {
      return true;
    }

    if (currentParts[index] < minimumParts[index]) {
      return false;
    }
  }

  return true;
}

function getPackageJson() {
  const packageJsonPath = resolve(process.cwd(), 'package.json');

  return JSON.parse(readFileSync(packageJsonPath, 'utf8')) as {
    dependencies?: DependencyMap;
    devDependencies?: DependencyMap;
  };
}

describe('FITorNOT deployment dependency floor', () => {
  it('keeps Next.js packages on the patched Railway-safe version line', () => {
    const packageJson = getPackageJson();
    const runtimeDependencies = packageJson.dependencies ?? {};
    const devDependencies = packageJson.devDependencies ?? {};

    expect(isVersionAtLeast(runtimeDependencies.next, '16.0.10')).toBe(true);
    expect(
      isVersionAtLeast(runtimeDependencies['@next/bundle-analyzer'], '16.0.10')
    ).toBe(true);
    expect(
      isVersionAtLeast(runtimeDependencies['@next/third-parties'], '16.0.10')
    ).toBe(true);
    expect(isVersionAtLeast(devDependencies['eslint-config-next'], '16.0.10')).toBe(
      true
    );
  });

  it('does not pin the vulnerable Next.js build in pnpm-lock.yaml', () => {
    const lockfilePath = resolve(process.cwd(), 'pnpm-lock.yaml');
    const lockfile = readFileSync(lockfilePath, 'utf8');

    expect(lockfile.includes('next@16.0.7')).toBe(false);
  });
});

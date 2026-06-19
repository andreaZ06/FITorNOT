import { revalidateTag, unstable_cache } from 'next/cache';

import { db } from '@/core/db';
import { envConfigs } from '@/config';
import { config } from '@/config/db/schema';
import {
  getAllSettingNames,
  publicSettingNames,
} from '@/shared/services/settings';

export type Config = typeof config.$inferSelect;
export type NewConfig = typeof config.$inferInsert;
export type UpdateConfig = Partial<Omit<NewConfig, 'name'>>;

export type Configs = Record<string, string>;

export const CACHE_TAG_CONFIGS = 'configs';

const MISSING_CONFIG_TABLE_PATTERNS = [
  /\brelation\s+"?config"?\s+does\s+not\s+exist\b/i,
  /\btable\b[^\n]*\bconfig\b[^\n]*\bdoesn'?t\s+exist\b/i,
  /\bno\s+such\s+table:\s*config\b/i,
];

function isMissingConfigTableError(error: unknown): boolean {
  let current = error;

  for (let depth = 0; depth < 4 && current; depth += 1) {
    const message =
      current instanceof Error
        ? current.message
        : typeof current === 'string'
          ? current
          : '';

    if (
      message &&
      MISSING_CONFIG_TABLE_PATTERNS.some((pattern) => pattern.test(message))
    ) {
      return true;
    }

    current =
      current && typeof current === 'object' && 'cause' in current
        ? (current as { cause?: unknown }).cause
        : null;
  }

  return false;
}

export async function saveConfigs(configs: Record<string, string>) {
  const result = await db().transaction(async (tx: any) => {
    const configEntries = Object.entries(configs);
    const results: any[] = [];

    for (const [name, configValue] of configEntries) {
      const [upsertResult] = await tx
        .insert(config)
        .values({ name, value: configValue })
        .onConflictDoUpdate({
          target: config.name,
          set: { value: configValue },
        })
        .returning();

      results.push(upsertResult);
    }

    return results;
  });

  revalidateTag(CACHE_TAG_CONFIGS, 'max');

  return result;
}

export async function addConfig(newConfig: NewConfig) {
  const [result] = await db().insert(config).values(newConfig).returning();
  revalidateTag(CACHE_TAG_CONFIGS, 'max');

  return result;
}

export const getConfigs = unstable_cache(
  async (): Promise<Configs> => {
    const configs: Record<string, string> = {};

    if (!envConfigs.database_url) {
      return configs;
    }

    let result;
    try {
      result = await db().select().from(config);
    } catch (error) {
      // Allow first deploys and fresh databases to build before the admin
      // config table has been created.
      if (isMissingConfigTableError(error)) {
        return configs;
      }
      throw error;
    }

    if (!result) {
      return configs;
    }

    for (const config of result) {
      configs[config.name] = config.value ?? '';
    }

    return configs;
  },
  ['configs'],
  {
    revalidate: 3600,
    tags: [CACHE_TAG_CONFIGS],
  }
);

export async function getAllConfigs(): Promise<Configs> {
  let dbConfigs: Configs = {};

  // only get configs from db in server side
  if (typeof window === 'undefined' && envConfigs.database_url) {
    try {
      dbConfigs = await getConfigs();
    } catch (e) {
      console.log(`get configs from db failed:`, e);
      dbConfigs = {};
    }
  }

  const settingNames = await getAllSettingNames();
  settingNames.forEach((key) => {
    const upperKey = key.toUpperCase();
    // use env configs if available
    if (process.env[upperKey]) {
      dbConfigs[key] = process.env[upperKey] ?? '';
    } else if (process.env[key]) {
      dbConfigs[key] = process.env[key] ?? '';
    }
  });

  const configs = {
    ...envConfigs,
    ...dbConfigs,
  };

  return configs;
}

export async function getPublicConfigs(): Promise<Configs> {
  let allConfigs = await getAllConfigs();

  const publicConfigs: Record<string, string> = {};

  // get public configs
  for (const key in allConfigs) {
    if (publicSettingNames.includes(key)) {
      publicConfigs[key] = String(allConfigs[key]);
    }
  }

  const configs = {
    ...publicConfigs,
  };

  return configs;
}

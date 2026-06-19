import type {
  FitOrNotHistoryEntry,
  FitOrNotPendingRequest,
} from './types';

const HISTORY_STORAGE_KEY = 'fitornot:history:v1';
const PENDING_STORAGE_PREFIX = 'fitornot:pending:';
const MAX_HISTORY_ENTRIES = 3;

function isBrowserReady() {
  return typeof window !== 'undefined';
}

function parseHistoryEntries(value: string | null): FitOrNotHistoryEntry[] {
  if (!value) {
    return [];
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed as FitOrNotHistoryEntry[];
  } catch {
    return [];
  }
}

export function getFitOrNotHistoryEntries(): FitOrNotHistoryEntry[] {
  if (!isBrowserReady()) {
    return [];
  }

  const entries = parseHistoryEntries(window.localStorage.getItem(HISTORY_STORAGE_KEY));
  return entries.sort((left, right) => right.createdAt.localeCompare(left.createdAt));
}

export function appendFitOrNotHistoryEntry(entry: FitOrNotHistoryEntry) {
  if (!isBrowserReady()) {
    return;
  }

  const existingEntries = getFitOrNotHistoryEntries().filter(
    (existingEntry) => existingEntry.id !== entry.id
  );
  const nextEntries = [entry, ...existingEntries]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, MAX_HISTORY_ENTRIES);

  window.localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(nextEntries));
}

export function savePendingFitOrNotRequest(request: FitOrNotPendingRequest) {
  if (!isBrowserReady()) {
    return;
  }

  window.sessionStorage.setItem(
    `${PENDING_STORAGE_PREFIX}${request.id}`,
    JSON.stringify(request)
  );
}

export function getPendingFitOrNotRequest(
  entryId: string
): FitOrNotPendingRequest | null {
  if (!isBrowserReady()) {
    return null;
  }

  const rawValue = window.sessionStorage.getItem(
    `${PENDING_STORAGE_PREFIX}${entryId}`
  );
  if (!rawValue) {
    return null;
  }

  try {
    return JSON.parse(rawValue) as FitOrNotPendingRequest;
  } catch {
    return null;
  }
}

export function clearPendingFitOrNotRequest(entryId: string) {
  if (!isBrowserReady()) {
    return;
  }

  window.sessionStorage.removeItem(`${PENDING_STORAGE_PREFIX}${entryId}`);
}

export { HISTORY_STORAGE_KEY, MAX_HISTORY_ENTRIES };

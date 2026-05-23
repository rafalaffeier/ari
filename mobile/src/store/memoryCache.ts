import AsyncStorage from "@react-native-async-storage/async-storage";

import type { JournalDay, JournalOverview, JournalSection, SearchResult, TimelineDay } from "../services/api";

const SESSION_KEY = "ari.mobile.session.v1";
const PENDING_KEY = "ari.mobile.pendingEntries.v1";

export type CachedSession = {
  token: string;
  userId: string;
  workspaceId: string | null;
};

export type PendingEntry = {
  id: string;
  workspaceId: string;
  day: string;
  section: JournalSection;
  text: string;
  createdAt: string;
};

const keyFor = (workspaceId: string, name: string) => `ari.mobile.${workspaceId}.${name}.v1`;
const dayKeyFor = (workspaceId: string, day: string, name: string) => `ari.mobile.${workspaceId}.${day}.${name}.v1`;

async function readJson<T>(key: string, fallback: T): Promise<T> {
  const value = await AsyncStorage.getItem(key);
  if (!value) return fallback;
  try {
    return JSON.parse(value) as T;
  } catch {
    return fallback;
  }
}

export const memoryCache = {
  loadSession: () => readJson<CachedSession | null>(SESSION_KEY, null),
  saveSession: (session: CachedSession) => AsyncStorage.setItem(SESSION_KEY, JSON.stringify(session)),
  clearSession: () => AsyncStorage.removeItem(SESSION_KEY),

  loadTimeline: (workspaceId: string) => readJson<TimelineDay[]>(keyFor(workspaceId, "timeline"), []),
  saveTimeline: (workspaceId: string, timeline: TimelineDay[]) =>
    AsyncStorage.setItem(keyFor(workspaceId, "timeline"), JSON.stringify(timeline)),

  loadDay: (workspaceId: string, day: string) => readJson<JournalDay | null>(dayKeyFor(workspaceId, day, "day"), null),
  saveDay: (workspaceId: string, day: string, value: JournalDay) =>
    AsyncStorage.setItem(dayKeyFor(workspaceId, day, "day"), JSON.stringify(value)),

  loadOverview: (workspaceId: string, day: string) =>
    readJson<JournalOverview | null>(dayKeyFor(workspaceId, day, "overview"), null),
  saveOverview: (workspaceId: string, day: string, value: JournalOverview) =>
    AsyncStorage.setItem(dayKeyFor(workspaceId, day, "overview"), JSON.stringify(value)),

  loadSearch: (workspaceId: string, query: string) =>
    readJson<SearchResult[]>(keyFor(workspaceId, `search.${query.trim().toLowerCase()}`), []),
  saveSearch: (workspaceId: string, query: string, value: SearchResult[]) =>
    AsyncStorage.setItem(keyFor(workspaceId, `search.${query.trim().toLowerCase()}`), JSON.stringify(value)),

  loadPendingEntries: () => readJson<PendingEntry[]>(PENDING_KEY, []),
  savePendingEntries: (entries: PendingEntry[]) => AsyncStorage.setItem(PENDING_KEY, JSON.stringify(entries)),
};

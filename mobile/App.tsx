import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import { api, JournalOverview, JournalSection, SearchResult, TimelineDay } from "./src/services/api";
import { useAuthStore } from "./src/store/auth";
import { memoryCache, PendingEntry } from "./src/store/memoryCache";

const SECTIONS: { key: JournalSection; label: string }[] = [
  { key: "tasks", label: "Tasks" },
  { key: "decisions", label: "Decisions" },
  { key: "pending", label: "Pending" },
  { key: "facts", label: "Facts" },
  { key: "chat", label: "Chat" },
  { key: "technical_events", label: "Tech" },
];

type Tab = "timeline" | "day" | "add" | "search";

function todayString() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export default function App() {
  const { token, userId, workspaceId, setSession, logout } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [tab, setTab] = useState<Tab>("timeline");
  const [timeline, setTimeline] = useState<TimelineDay[]>([]);
  const [selectedDay, setSelectedDay] = useState(todayString());
  const [overview, setOverview] = useState<JournalOverview | null>(null);
  const [dayContent, setDayContent] = useState("");
  const [section, setSection] = useState<JournalSection>("tasks");
  const [entryText, setEntryText] = useState("");
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [pendingEntries, setPendingEntries] = useState<PendingEntry[]>([]);
  const [isOffline, setIsOffline] = useState(false);
  const [isBusy, setIsBusy] = useState(false);
  const [status, setStatus] = useState("Ready");

  const signedIn = Boolean(token && workspaceId);

  useEffect(() => {
    memoryCache.loadSession().then((session) => {
      if (session) setSession(session.token, session.userId, session.workspaceId);
    });
    memoryCache.loadPendingEntries().then(setPendingEntries);
  }, [setSession]);

  useEffect(() => {
    if (!workspaceId) return;
    memoryCache.loadTimeline(workspaceId).then(setTimeline);
    memoryCache.loadDay(workspaceId, selectedDay).then((cached) => {
      if (cached) setDayContent(cached.content);
    });
    memoryCache.loadOverview(workspaceId, selectedDay).then(setOverview);
  }, [workspaceId, selectedDay]);

  useEffect(() => {
    if (signedIn) refreshTimeline();
  }, [signedIn]);

  const visiblePending = useMemo(
    () => pendingEntries.filter((entry) => entry.workspaceId === workspaceId),
    [pendingEntries, workspaceId],
  );

  async function authenticate() {
    if (!email.trim() || !password) {
      Alert.alert("Missing login", "Email and password are required.");
      return;
    }
    setIsBusy(true);
    setStatus(mode === "login" ? "Signing in" : "Creating account");
    try {
      const auth = mode === "login" ? await api.login(email.trim(), password) : await api.register(email.trim(), password);
      setSession(auth.access_token, auth.user_id, auth.default_workspace_id);
      await memoryCache.saveSession({
        token: auth.access_token,
        userId: auth.user_id,
        workspaceId: auth.default_workspace_id,
      });
      setIsOffline(false);
      setStatus("Synced");
    } catch (error) {
      setIsOffline(true);
      setStatus(error instanceof Error ? error.message : "Unable to sign in");
    } finally {
      setIsBusy(false);
    }
  }

  async function signOut() {
    logout();
    await memoryCache.clearSession();
    setTimeline([]);
    setOverview(null);
    setDayContent("");
    setStatus("Signed out");
  }

  async function refreshTimeline() {
    if (!token || !workspaceId) return;
    setIsBusy(true);
    try {
      const fresh = await api.getTimeline(token, workspaceId);
      setTimeline(fresh);
      await memoryCache.saveTimeline(workspaceId, fresh);
      setIsOffline(false);
      setStatus("Timeline synced");
      await flushPendingEntries();
    } catch (error) {
      setIsOffline(true);
      setStatus("Showing cached timeline");
    } finally {
      setIsBusy(false);
    }
  }

  async function loadDay(day: string) {
    if (!token || !workspaceId) return;
    setSelectedDay(day);
    setTab("day");
    setIsBusy(true);
    try {
      const [freshDay, freshOverview] = await Promise.all([
        api.getJournalDay(token, workspaceId, day),
        api.getJournalOverview(token, workspaceId, day),
      ]);
      setDayContent(freshDay.content);
      setOverview(freshOverview);
      await memoryCache.saveDay(workspaceId, day, freshDay);
      await memoryCache.saveOverview(workspaceId, day, freshOverview);
      setIsOffline(false);
      setStatus(`${day} synced`);
    } catch (error) {
      const [cachedDay, cachedOverview] = await Promise.all([
        memoryCache.loadDay(workspaceId, day),
        memoryCache.loadOverview(workspaceId, day),
      ]);
      if (cachedDay) setDayContent(cachedDay.content);
      if (cachedOverview) setOverview(cachedOverview);
      setIsOffline(true);
      setStatus(cachedDay || cachedOverview ? "Showing cached day" : "No cached copy for this day");
    } finally {
      setIsBusy(false);
    }
  }

  async function addEntry() {
    if (!token || !workspaceId || !entryText.trim()) return;
    const text = entryText.trim();
    setEntryText("");
    setIsBusy(true);
    try {
      await api.addJournalEntry(token, workspaceId, selectedDay, section, text);
      setIsOffline(false);
      setStatus("Entry saved");
      await loadDay(selectedDay);
      await refreshTimeline();
    } catch (error) {
      const pending = [
        ...pendingEntries,
        {
          id: `${Date.now()}`,
          workspaceId,
          day: selectedDay,
          section,
          text,
          createdAt: new Date().toISOString(),
        },
      ];
      setPendingEntries(pending);
      await memoryCache.savePendingEntries(pending);
      setIsOffline(true);
      setStatus("Entry queued offline");
    } finally {
      setIsBusy(false);
    }
  }

  async function flushPendingEntries() {
    if (!token || !workspaceId) return;
    const queue = await memoryCache.loadPendingEntries();
    const remaining: PendingEntry[] = [];
    for (const pending of queue) {
      if (pending.workspaceId !== workspaceId) {
        remaining.push(pending);
        continue;
      }
      try {
        await api.addJournalEntry(token, pending.workspaceId, pending.day, pending.section, pending.text);
      } catch {
        remaining.push(pending);
      }
    }
    setPendingEntries(remaining);
    await memoryCache.savePendingEntries(remaining);
    if (remaining.length !== queue.length) setStatus("Offline queue synced");
  }

  async function search() {
    if (!token || !workspaceId || !query.trim()) return;
    setIsBusy(true);
    try {
      const fresh = await api.searchMemory(token, workspaceId, query);
      setResults(fresh);
      await memoryCache.saveSearch(workspaceId, query, fresh);
      setIsOffline(false);
      setStatus("Search synced");
    } catch {
      const cached = await memoryCache.loadSearch(workspaceId, query);
      setResults(cached);
      setIsOffline(true);
      setStatus(cached.length ? "Showing cached search" : "No cached results");
    } finally {
      setIsBusy(false);
    }
  }

  if (!signedIn) {
    return (
      <SafeAreaView style={styles.screen}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.auth}>
          <Text style={styles.brand}>ARI Memory</Text>
          <View style={styles.segment}>
            <SegmentButton active={mode === "login"} label="Login" onPress={() => setMode("login")} />
            <SegmentButton active={mode === "register"} label="Register" onPress={() => setMode("register")} />
          </View>
          <TextInput
            autoCapitalize="none"
            keyboardType="email-address"
            onChangeText={setEmail}
            placeholder="email"
            style={styles.input}
            value={email}
          />
          <TextInput
            onChangeText={setPassword}
            placeholder="password"
            secureTextEntry
            style={styles.input}
            value={password}
          />
          <Pressable disabled={isBusy} onPress={authenticate} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>{isBusy ? "Working..." : mode === "login" ? "Sign in" : "Create"}</Text>
          </Pressable>
          <StatusLine isBusy={isBusy} isOffline={isOffline} status={status} />
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        <View>
          <Text style={styles.brandSmall}>ARI Memory</Text>
          <Text style={styles.meta}>{userId?.slice(0, 8)} / {workspaceId?.slice(0, 8)}</Text>
        </View>
        <Pressable onPress={signOut} style={styles.ghostButton}>
          <Text style={styles.ghostButtonText}>Logout</Text>
        </Pressable>
      </View>

      <View style={styles.segment}>
        <SegmentButton active={tab === "timeline"} label="Timeline" onPress={() => setTab("timeline")} />
        <SegmentButton active={tab === "day"} label="Day" onPress={() => setTab("day")} />
        <SegmentButton active={tab === "add"} label="Add" onPress={() => setTab("add")} />
        <SegmentButton active={tab === "search"} label="Search" onPress={() => setTab("search")} />
      </View>

      <StatusLine isBusy={isBusy} isOffline={isOffline || visiblePending.length > 0} status={status} />

      <ScrollView contentContainerStyle={styles.content}>
        {tab === "timeline" && (
          <View style={styles.panel}>
            <View style={styles.rowBetween}>
              <Text style={styles.title}>Timeline</Text>
              <Pressable onPress={refreshTimeline} style={styles.ghostButton}>
                <Text style={styles.ghostButtonText}>Sync</Text>
              </Pressable>
            </View>
            {timeline.map((item) => (
              <Pressable key={item.date} onPress={() => loadDay(item.date)} style={styles.listItem}>
                <Text style={styles.listDate}>{item.date}</Text>
                <Text style={styles.listMeta}>{item.entry_count} entries</Text>
                <Text style={styles.chips}>{sectionSummary(item.sections)}</Text>
              </Pressable>
            ))}
            {!timeline.length && <Text style={styles.empty}>No days yet.</Text>}
          </View>
        )}

        {tab === "day" && (
          <View style={styles.panel}>
            <View style={styles.rowBetween}>
              <TextInput onChangeText={setSelectedDay} style={[styles.input, styles.dateInput]} value={selectedDay} />
              <Pressable onPress={() => loadDay(selectedDay)} style={styles.ghostButton}>
                <Text style={styles.ghostButtonText}>Load</Text>
              </Pressable>
            </View>
            <Overview overview={overview} />
            <Text style={styles.markdown}>{dayContent}</Text>
          </View>
        )}

        {tab === "add" && (
          <View style={styles.panel}>
            <Text style={styles.title}>Add entry</Text>
            <TextInput onChangeText={setSelectedDay} style={styles.input} value={selectedDay} />
            <View style={styles.sectionGrid}>
              {SECTIONS.map((item) => (
                <SegmentButton
                  key={item.key}
                  active={section === item.key}
                  label={item.label}
                  onPress={() => setSection(item.key)}
                />
              ))}
            </View>
            <TextInput
              multiline
              onChangeText={setEntryText}
              placeholder="Write a memory entry"
              style={[styles.input, styles.textarea]}
              value={entryText}
            />
            <Pressable disabled={isBusy || !entryText.trim()} onPress={addEntry} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Save entry</Text>
            </Pressable>
            {visiblePending.map((entry) => (
              <Text key={entry.id} style={styles.pending}>Queued: {entry.day} / {entry.section}</Text>
            ))}
          </View>
        )}

        {tab === "search" && (
          <View style={styles.panel}>
            <Text style={styles.title}>Search</Text>
            <View style={styles.rowBetween}>
              <TextInput onChangeText={setQuery} placeholder="query" style={[styles.input, styles.searchInput]} value={query} />
              <Pressable onPress={search} style={styles.ghostButton}>
                <Text style={styles.ghostButtonText}>Go</Text>
              </Pressable>
            </View>
            {results.map((item) => (
              <Pressable key={`${item.path}-${item.line_number}`} onPress={() => loadDay(item.date)} style={styles.listItem}>
                <Text style={styles.listDate}>{item.date}</Text>
                <Text style={styles.resultLine}>{item.line}</Text>
              </Pressable>
            ))}
            {!results.length && <Text style={styles.empty}>No results.</Text>}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function SegmentButton({ active, label, onPress }: { active: boolean; label: string; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={[styles.segmentButton, active && styles.segmentButtonActive]}>
      <Text style={[styles.segmentText, active && styles.segmentTextActive]}>{label}</Text>
    </Pressable>
  );
}

function StatusLine({ isBusy, isOffline, status }: { isBusy: boolean; isOffline: boolean; status: string }) {
  return (
    <View style={styles.status}>
      {isBusy && <ActivityIndicator size="small" color="#3d5a80" />}
      <View style={[styles.statusDot, isOffline ? styles.statusDotOffline : styles.statusDotOnline]} />
      <Text style={styles.statusText}>{isOffline ? "Offline cache" : status}</Text>
    </View>
  );
}

function Overview({ overview }: { overview: JournalOverview | null }) {
  if (!overview) return null;
  return (
    <View style={styles.overview}>
      {SECTIONS.map((section) => {
        const entries = overview.sections[section.key] ?? [];
        return (
          <View key={section.key} style={styles.overviewSection}>
            <Text style={styles.overviewTitle}>{section.label}</Text>
            <Text style={styles.overviewCount}>{entries.length}</Text>
          </View>
        );
      })}
    </View>
  );
}

function sectionSummary(sections: Record<string, number>) {
  return Object.entries(sections)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => `${name}:${count}`)
    .join("  ");
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: "#f7f2ea",
  },
  auth: {
    flex: 1,
    justifyContent: "center",
    padding: 20,
    gap: 12,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 16,
    paddingBottom: 8,
  },
  brand: {
    color: "#17202a",
    fontSize: 34,
    fontWeight: "800",
    marginBottom: 10,
  },
  brandSmall: {
    color: "#17202a",
    fontSize: 22,
    fontWeight: "800",
  },
  meta: {
    color: "#667085",
    fontSize: 12,
    marginTop: 2,
  },
  segment: {
    backgroundColor: "#e8dfd2",
    borderRadius: 8,
    flexDirection: "row",
    gap: 4,
    marginHorizontal: 16,
    padding: 4,
  },
  segmentButton: {
    alignItems: "center",
    borderRadius: 6,
    flex: 1,
    minHeight: 38,
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  segmentButtonActive: {
    backgroundColor: "#17202a",
  },
  segmentText: {
    color: "#394150",
    fontSize: 13,
    fontWeight: "700",
  },
  segmentTextActive: {
    color: "#ffffff",
  },
  status: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    minHeight: 30,
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  statusDot: {
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  statusDotOnline: {
    backgroundColor: "#2f855a",
  },
  statusDotOffline: {
    backgroundColor: "#c05621",
  },
  statusText: {
    color: "#475467",
    fontSize: 13,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  panel: {
    gap: 12,
  },
  title: {
    color: "#17202a",
    fontSize: 22,
    fontWeight: "800",
  },
  rowBetween: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  input: {
    backgroundColor: "#ffffff",
    borderColor: "#d0d5dd",
    borderRadius: 8,
    borderWidth: 1,
    color: "#17202a",
    fontSize: 16,
    minHeight: 48,
    paddingHorizontal: 14,
  },
  dateInput: {
    flex: 1,
  },
  searchInput: {
    flex: 1,
  },
  textarea: {
    minHeight: 150,
    paddingTop: 14,
    textAlignVertical: "top",
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#3d5a80",
    borderRadius: 8,
    minHeight: 50,
    justifyContent: "center",
  },
  primaryButtonText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "800",
  },
  ghostButton: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#d0d5dd",
    borderRadius: 8,
    borderWidth: 1,
    minHeight: 42,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  ghostButtonText: {
    color: "#17202a",
    fontWeight: "800",
  },
  listItem: {
    backgroundColor: "#ffffff",
    borderColor: "#d0d5dd",
    borderRadius: 8,
    borderWidth: 1,
    gap: 6,
    padding: 14,
  },
  listDate: {
    color: "#17202a",
    fontSize: 17,
    fontWeight: "800",
  },
  listMeta: {
    color: "#475467",
    fontSize: 14,
  },
  chips: {
    color: "#3d5a80",
    fontSize: 12,
    fontWeight: "700",
  },
  empty: {
    color: "#667085",
    fontSize: 15,
    paddingVertical: 20,
  },
  overview: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  overviewSection: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#d0d5dd",
    borderRadius: 8,
    borderWidth: 1,
    flexBasis: "30%",
    flexGrow: 1,
    minHeight: 62,
    justifyContent: "center",
  },
  overviewTitle: {
    color: "#475467",
    fontSize: 12,
    fontWeight: "700",
  },
  overviewCount: {
    color: "#17202a",
    fontSize: 20,
    fontWeight: "800",
  },
  markdown: {
    backgroundColor: "#ffffff",
    borderColor: "#d0d5dd",
    borderRadius: 8,
    borderWidth: 1,
    color: "#17202a",
    fontFamily: Platform.select({ ios: "Menlo", android: "monospace", default: "monospace" }),
    fontSize: 13,
    lineHeight: 20,
    padding: 14,
  },
  sectionGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 8,
  },
  pending: {
    color: "#c05621",
    fontSize: 13,
    fontWeight: "700",
  },
  resultLine: {
    color: "#344054",
    fontSize: 14,
    lineHeight: 20,
  },
});

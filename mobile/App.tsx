import { useEffect, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Linking,
  NativeModules,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

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
type TranslationLanguage = "en" | "es";
type AppLanguage = string;

const LANGUAGE_KEY = "ari.appLanguage";
const LANGUAGE_OPTIONS = [
  ["en", "English"],
  ["ru", "Русский"],
  ["uk", "Українська"],
  ["es", "Español"],
  ["de", "Deutsch"],
  ["it", "Italiano"],
  ["pt", "Português"],
] as const;

const STRINGS = {
  en: {
    accessLight: "Access your light",
    add: "Add",
    addEntry: "Add entry",
    alignMe: "Align me ->",
    create: "Create",
    createAccount: "Creating account",
    createLight: "Create light ->",
    day: "Day",
    emailPasswordRequired: "Email and password are required.",
    entries: "entries",
    exit: "Exit",
    googleActive: "Google session active",
    googleCodePlaceholder: "Paste ARI Google code",
    googleMissingCode: "Paste the ARI Google login code first.",
    googleMissingTitle: "Missing code",
    googleOpen: "Opening Google",
    googleOpenError: "Unable to open Google",
    googlePaste: "Paste the ARI code from your browser",
    googleVerify: "Verify Google",
    googleVerifying: "Verifying Google",
    language: "Language",
    load: "Load",
    login: "Login",
    missingLogin: "Missing login",
    noCache: "No cached copy for this day",
    noDays: "No days yet.",
    noResults: "No results.",
    offlineCache: "Offline cache",
    password: "password",
    query: "query",
    queued: "Queued",
    ready: "Ready",
    saveEntry: "Save entry",
    search: "Search",
    searchSynced: "Search synced",
    selectLanguage: "Language",
    signedOut: "Signed out",
    signingIn: "Signing in",
    sync: "Sync",
    synced: "Synced",
    timeline: "Timeline",
    timelineSynced: "Timeline synced",
    unableSignIn: "Unable to sign in",
    unableVerifyGoogle: "Unable to verify Google",
    working: "Working...",
    writeMemory: "Write a memory entry",
  },
  es: {
    accessLight: "Accede a tu luz",
    add: "Agregar",
    addEntry: "Agregar entrada",
    alignMe: "Entrar ->",
    create: "Crear",
    createAccount: "Creando cuenta",
    createLight: "Crear luz ->",
    day: "Dia",
    emailPasswordRequired: "El email y la contrasena son obligatorios.",
    entries: "entradas",
    exit: "Salir",
    googleActive: "Sesion de Google activa",
    googleCodePlaceholder: "Pega el codigo de Google de ARI",
    googleMissingCode: "Pega primero el codigo de inicio de Google de ARI.",
    googleMissingTitle: "Falta el codigo",
    googleOpen: "Abriendo Google",
    googleOpenError: "No se pudo abrir Google",
    googlePaste: "Pega el codigo de ARI desde tu navegador",
    googleVerify: "Verificar Google",
    googleVerifying: "Verificando Google",
    language: "Idioma",
    load: "Cargar",
    login: "Entrar",
    missingLogin: "Falta el acceso",
    noCache: "No hay copia cacheada de este dia",
    noDays: "Todavia no hay dias.",
    noResults: "Sin resultados.",
    offlineCache: "Cache sin conexion",
    password: "contrasena",
    query: "consulta",
    queued: "En cola",
    ready: "Listo",
    saveEntry: "Guardar entrada",
    search: "Buscar",
    searchSynced: "Busqueda sincronizada",
    selectLanguage: "Idioma",
    signedOut: "Sesion cerrada",
    signingIn: "Entrando",
    sync: "Sincronizar",
    synced: "Sincronizado",
    timeline: "Linea temporal",
    timelineSynced: "Linea temporal sincronizada",
    unableSignIn: "No se pudo iniciar sesion",
    unableVerifyGoogle: "No se pudo verificar Google",
    working: "Trabajando...",
    writeMemory: "Escribe una entrada de memoria",
  },
} as const;

const SECTION_LABELS: Record<TranslationLanguage, Record<JournalSection, string>> = {
  en: {
    tasks: "Tasks",
    decisions: "Decisions",
    pending: "Pending",
    facts: "Facts",
    chat: "Chat",
    technical_events: "Tech",
  },
  es: {
    tasks: "Tareas",
    decisions: "Decisiones",
    pending: "Pendiente",
    facts: "Datos",
    chat: "Chat",
    technical_events: "Tecnico",
  },
};

function normalizeLanguage(value?: string | null): AppLanguage {
  return (value || "en").toLowerCase().replace("_", "-").split("-")[0] || "en";
}

function translationLanguage(value?: string | null): TranslationLanguage {
  return normalizeLanguage(value) === "es" ? "es" : "en";
}

function deviceLanguage(): AppLanguage {
  const settings = NativeModules.SettingsManager?.settings;
  const iosLocale = settings?.AppleLocale || settings?.AppleLanguages?.[0];
  const androidLocale = NativeModules.I18nManager?.localeIdentifier;
  return normalizeLanguage(iosLocale || androidLocale);
}

function todayString() {
  const now = new Date();
  const offset = now.getTimezoneOffset() * 60000;
  return new Date(now.getTime() - offset).toISOString().slice(0, 10);
}

export default function App() {
  const { token, userId, workspaceId, setSession, logout } = useAuthStore();
  const [language, setLanguage] = useState<AppLanguage>(deviceLanguage());
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [googleCode, setGoogleCode] = useState("");
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
  const [status, setStatus] = useState<string>(STRINGS[translationLanguage(deviceLanguage())].ready);
  const uiLanguage = translationLanguage(language);
  const t = STRINGS[uiLanguage];
  const sections = useMemo(
    () => SECTIONS.map((item) => ({ ...item, label: SECTION_LABELS[uiLanguage][item.key] })),
    [uiLanguage],
  );

  const signedIn = Boolean(token && workspaceId);

  useEffect(() => {
    AsyncStorage.getItem(LANGUAGE_KEY).then((stored) => {
      if (stored) setLanguage(normalizeLanguage(stored));
    });
    memoryCache.loadSession().then((session) => {
      if (session) setSession(session.token, session.userId, session.workspaceId);
    });
    memoryCache.loadPendingEntries().then(setPendingEntries);
  }, [setSession]);

  function changeLanguage(nextLanguage: AppLanguage) {
    setLanguage(nextLanguage);
    AsyncStorage.setItem(LANGUAGE_KEY, nextLanguage);
  }

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
      Alert.alert(t.missingLogin, t.emailPasswordRequired);
      return;
    }
    setIsBusy(true);
    setStatus(mode === "login" ? t.signingIn : t.createAccount);
    try {
      const auth = mode === "login" ? await api.login(email.trim(), password) : await api.register(email.trim(), password);
      setSession(auth.access_token, auth.user_id, auth.default_workspace_id);
      await memoryCache.saveSession({
        token: auth.access_token,
        userId: auth.user_id,
        workspaceId: auth.default_workspace_id,
      });
      setIsOffline(false);
      setStatus(t.synced);
    } catch (error) {
      setIsOffline(true);
      setStatus(error instanceof Error ? error.message : t.unableSignIn);
    } finally {
      setIsBusy(false);
    }
  }

  async function openGoogleLogin() {
    setStatus(t.googleOpen);
    try {
      await Linking.openURL(api.googleAuthUrl("mobile"));
      setStatus(t.googlePaste);
    } catch (error) {
      setIsOffline(true);
      setStatus(t.googleOpenError);
    }
  }

  async function exchangeGoogleCode() {
    if (!googleCode.trim()) {
      Alert.alert(t.googleMissingTitle, t.googleMissingCode);
      return;
    }
    setIsBusy(true);
    setStatus(t.googleVerifying);
    try {
      const auth = await api.exchangeGoogleCode(googleCode.trim());
      setSession(auth.access_token, auth.user_id, auth.default_workspace_id);
      await memoryCache.saveSession({
        token: auth.access_token,
        userId: auth.user_id,
        workspaceId: auth.default_workspace_id,
      });
      setGoogleCode("");
      setIsOffline(false);
      setStatus(t.googleActive);
    } catch (error) {
      setIsOffline(true);
      setStatus(error instanceof Error ? error.message : t.unableVerifyGoogle);
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
    setStatus(t.signedOut);
  }

  async function refreshTimeline() {
    if (!token || !workspaceId) return;
    setIsBusy(true);
    try {
      const fresh = await api.getTimeline(token, workspaceId);
      setTimeline(fresh);
      await memoryCache.saveTimeline(workspaceId, fresh);
      setIsOffline(false);
      setStatus(t.timelineSynced);
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
      setStatus(cachedDay || cachedOverview ? "Showing cached day" : t.noCache);
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
      setStatus(uiLanguage === "es" ? "Entrada guardada" : "Entry saved");
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
      setStatus(uiLanguage === "es" ? "Entrada en cola sin conexion" : "Entry queued offline");
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
      setStatus(t.searchSynced);
    } catch {
      const cached = await memoryCache.loadSearch(workspaceId, query);
      setResults(cached);
      setIsOffline(true);
      setStatus(cached.length ? "Showing cached search" : t.noResults);
    } finally {
      setIsBusy(false);
    }
  }

  if (!signedIn) {
    return (
      <SafeAreaView style={styles.screen}>
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.auth}>
          <View style={styles.authCard}>
            <Text style={styles.sunMark}>☉</Text>
            <Text style={styles.brand}>Ari</Text>
            <Text style={styles.brandSub}>Solara · Quantum Intelligent</Text>
            <Text style={styles.authTitle}>{t.accessLight}</Text>
            <View style={styles.languageRow}>
              <Text style={styles.languageLabel}>{t.language}</Text>
              <LanguagePicker language={language} onChange={changeLanguage} />
            </View>
            <View style={styles.segment}>
              <SegmentButton active={mode === "login"} label={t.login} onPress={() => setMode("login")} />
              <SegmentButton active={mode === "register"} label={t.create} onPress={() => setMode("register")} />
            </View>
            {mode === "login" && (
              <>
                <Pressable disabled={isBusy} onPress={openGoogleLogin} style={styles.googleButton}>
                  <Text style={styles.googleButtonText}>☉ Continue with Google</Text>
                </Pressable>
                <TextInput
                  autoCapitalize="none"
                  onChangeText={setGoogleCode}
                  placeholder={t.googleCodePlaceholder}
                  placeholderTextColor="rgba(201,169,110,0.34)"
                  style={styles.input}
                  value={googleCode}
                />
                <Pressable disabled={isBusy || !googleCode.trim()} onPress={exchangeGoogleCode} style={styles.ghostButton}>
                  <Text style={styles.ghostButtonText}>{t.googleVerify}</Text>
                </Pressable>
              </>
            )}
            <TextInput
              autoCapitalize="none"
              keyboardType="email-address"
              onChangeText={setEmail}
              placeholder="soul@ari.ai"
              placeholderTextColor="rgba(201,169,110,0.34)"
              style={styles.input}
              value={email}
            />
            <TextInput
              onChangeText={setPassword}
              placeholder={t.password}
              placeholderTextColor="rgba(201,169,110,0.34)"
              secureTextEntry
              style={styles.input}
              value={password}
            />
            <Pressable disabled={isBusy} onPress={authenticate} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>{isBusy ? t.working : mode === "login" ? t.alignMe : t.createLight}</Text>
            </Pressable>
            <StatusLine isBusy={isBusy} isOffline={isOffline} offlineLabel={t.offlineCache} status={status} />
          </View>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        <View>
          <Text style={styles.brandSmall}>Ari</Text>
          <Text style={styles.meta}>Solara · {userId?.slice(0, 8)} · {workspaceId?.slice(0, 8)}</Text>
        </View>
        <Pressable onPress={signOut} style={styles.ghostButton}>
          <Text style={styles.ghostButtonText}>{t.exit}</Text>
        </Pressable>
      </View>

      <View style={styles.languageStrip}>
        <Text style={styles.languageLabel}>{t.selectLanguage}</Text>
        <LanguagePicker language={language} onChange={changeLanguage} />
      </View>

      <View style={styles.segment}>
        <SegmentButton active={tab === "timeline"} label={t.timeline} onPress={() => setTab("timeline")} />
        <SegmentButton active={tab === "day"} label={t.day} onPress={() => setTab("day")} />
        <SegmentButton active={tab === "add"} label={t.add} onPress={() => setTab("add")} />
        <SegmentButton active={tab === "search"} label={t.search} onPress={() => setTab("search")} />
      </View>

      <StatusLine isBusy={isBusy} isOffline={isOffline || visiblePending.length > 0} offlineLabel={t.offlineCache} status={status} />

      <ScrollView contentContainerStyle={styles.content}>
        {tab === "timeline" && (
          <View style={styles.panel}>
            <View style={styles.rowBetween}>
              <Text style={styles.title}>{t.timeline}</Text>
              <Pressable onPress={refreshTimeline} style={styles.ghostButton}>
                <Text style={styles.ghostButtonText}>{t.sync}</Text>
              </Pressable>
            </View>
            {timeline.map((item) => (
              <Pressable key={item.date} onPress={() => loadDay(item.date)} style={styles.listItem}>
                <Text style={styles.listDate}>{item.date}</Text>
                <Text style={styles.listMeta}>{item.entry_count} {t.entries}</Text>
                <Text style={styles.chips}>{sectionSummary(item.sections)}</Text>
              </Pressable>
            ))}
            {!timeline.length && <Text style={styles.empty}>{t.noDays}</Text>}
          </View>
        )}

        {tab === "day" && (
          <View style={styles.panel}>
            <View style={styles.rowBetween}>
              <TextInput onChangeText={setSelectedDay} style={[styles.input, styles.dateInput]} value={selectedDay} />
              <Pressable onPress={() => loadDay(selectedDay)} style={styles.ghostButton}>
                <Text style={styles.ghostButtonText}>{t.load}</Text>
              </Pressable>
            </View>
            <Overview overview={overview} sections={sections} />
            <Text style={styles.markdown}>{dayContent}</Text>
          </View>
        )}

        {tab === "add" && (
          <View style={styles.panel}>
            <Text style={styles.title}>{t.addEntry}</Text>
            <TextInput onChangeText={setSelectedDay} style={styles.input} value={selectedDay} />
            <View style={styles.sectionGrid}>
              {sections.map((item) => (
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
              placeholder={t.writeMemory}
              style={[styles.input, styles.textarea]}
              value={entryText}
            />
            <Pressable disabled={isBusy || !entryText.trim()} onPress={addEntry} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>{t.saveEntry}</Text>
            </Pressable>
            {visiblePending.map((entry) => (
              <Text key={entry.id} style={styles.pending}>{t.queued}: {entry.day} / {entry.section}</Text>
            ))}
          </View>
        )}

        {tab === "search" && (
          <View style={styles.panel}>
            <Text style={styles.title}>{t.search}</Text>
            <View style={styles.rowBetween}>
              <TextInput onChangeText={setQuery} placeholder={t.query} style={[styles.input, styles.searchInput]} value={query} />
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
            {!results.length && <Text style={styles.empty}>{t.noResults}</Text>}
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

function LanguagePicker({ language, onChange }: { language: string; onChange: (language: string) => void }) {
  const options = LANGUAGE_OPTIONS.some(([code]) => code === language)
    ? LANGUAGE_OPTIONS
    : ([[language, language.toUpperCase()], ...LANGUAGE_OPTIONS] as const);
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.languagePicker}>
      {options.map(([code, label]) => (
        <Pressable
          key={code}
          onPress={() => onChange(code)}
          style={[styles.languageOption, language === code && styles.languageOptionActive]}
        >
          <Text style={[styles.languageOptionText, language === code && styles.languageOptionTextActive]}>{label}</Text>
        </Pressable>
      ))}
      <TextInput
        autoCapitalize="none"
        autoCorrect={false}
        onChangeText={(value) => onChange(normalizeLanguage(value))}
        placeholder="code"
        placeholderTextColor="rgba(201,169,110,0.34)"
        style={styles.languageCodeInput}
        value={language}
      />
    </ScrollView>
  );
}

function StatusLine({
  isBusy,
  isOffline,
  offlineLabel,
  status,
}: {
  isBusy: boolean;
  isOffline: boolean;
  offlineLabel: string;
  status: string;
}) {
  return (
    <View style={styles.status}>
      {isBusy && <ActivityIndicator size="small" color="#C9A96E" />}
      <View style={[styles.statusDot, isOffline ? styles.statusDotOffline : styles.statusDotOnline]} />
      <Text style={styles.statusText}>{isOffline ? offlineLabel : status}</Text>
    </View>
  );
}

function Overview({
  overview,
  sections,
}: {
  overview: JournalOverview | null;
  sections: { key: JournalSection; label: string }[];
}) {
  if (!overview) return null;
  return (
    <View style={styles.overview}>
      {sections.map((section) => {
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
    backgroundColor: "#1A1208",
  },
  auth: {
    flex: 1,
    justifyContent: "center",
    padding: 18,
  },
  authCard: {
    backgroundColor: "rgba(20, 12, 4, 0.92)",
    borderColor: "rgba(201, 169, 110, 0.24)",
    borderRadius: 2,
    borderWidth: 1,
    gap: 14,
    padding: 26,
  },
  sunMark: {
    color: "#C9A96E",
    fontSize: 32,
    textAlign: "center",
  },
  header: {
    alignItems: "center",
    backgroundColor: "rgba(20, 12, 4, 0.84)",
    borderBottomColor: "rgba(201, 169, 110, 0.18)",
    borderBottomWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    padding: 18,
  },
  brand: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 44,
    fontStyle: "italic",
    fontWeight: "300",
    letterSpacing: 6,
    textAlign: "center",
  },
  brandSub: {
    color: "rgba(201, 169, 110, 0.48)",
    fontSize: 9,
    letterSpacing: 3,
    marginBottom: 12,
    textAlign: "center",
    textTransform: "uppercase",
  },
  authTitle: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 22,
    fontStyle: "italic",
    fontWeight: "300",
    marginBottom: 2,
    textAlign: "center",
  },
  brandSmall: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 32,
    fontStyle: "italic",
    fontWeight: "300",
    letterSpacing: 5,
  },
  meta: {
    color: "rgba(201, 169, 110, 0.42)",
    fontSize: 9,
    letterSpacing: 2,
    marginTop: 2,
    textTransform: "uppercase",
  },
  segment: {
    backgroundColor: "rgba(201, 169, 110, 0.04)",
    borderColor: "rgba(201, 169, 110, 0.16)",
    borderRadius: 2,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    marginHorizontal: 16,
    padding: 6,
  },
  segmentButton: {
    alignItems: "center",
    borderColor: "transparent",
    borderRadius: 1,
    borderWidth: 1,
    flex: 1,
    minHeight: 38,
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  segmentButtonActive: {
    backgroundColor: "rgba(201, 169, 110, 0.08)",
    borderColor: "rgba(201, 169, 110, 0.42)",
  },
  segmentText: {
    color: "rgba(201, 169, 110, 0.48)",
    fontSize: 10,
    fontWeight: "500",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  segmentTextActive: {
    color: "#F7F2EC",
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
    backgroundColor: "#C9A96E",
  },
  statusDotOffline: {
    backgroundColor: "#C4836A",
  },
  statusText: {
    color: "rgba(247, 242, 236, 0.68)",
    fontSize: 11,
    letterSpacing: 1,
  },
  languageRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  languageStrip: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingTop: 10,
  },
  languageLabel: {
    color: "rgba(201, 169, 110, 0.58)",
    fontSize: 10,
    fontWeight: "500",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  languageButtons: {
    flexDirection: "row",
    gap: 8,
    minWidth: 130,
  },
  languagePicker: {
    flex: 1,
    maxHeight: 40,
  },
  languageOption: {
    alignItems: "center",
    borderColor: "rgba(201, 169, 110, 0.18)",
    borderRadius: 1,
    borderWidth: 1,
    justifyContent: "center",
    marginRight: 8,
    minHeight: 36,
    paddingHorizontal: 12,
  },
  languageOptionActive: {
    backgroundColor: "rgba(201, 169, 110, 0.08)",
    borderColor: "rgba(201, 169, 110, 0.48)",
  },
  languageOptionText: {
    color: "rgba(201, 169, 110, 0.58)",
    fontSize: 10,
    fontWeight: "500",
  },
  languageOptionTextActive: {
    color: "#F7F2EC",
  },
  languageCodeInput: {
    borderColor: "rgba(201, 169, 110, 0.18)",
    borderRadius: 1,
    borderWidth: 1,
    color: "#F7F2EC",
    fontSize: 12,
    marginRight: 8,
    minHeight: 36,
    minWidth: 58,
    paddingHorizontal: 10,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  panel: {
    gap: 12,
  },
  title: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 24,
    fontStyle: "italic",
    fontWeight: "300",
  },
  rowBetween: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  input: {
    backgroundColor: "rgba(20, 12, 4, 0.64)",
    borderColor: "rgba(201, 169, 110, 0.2)",
    borderRadius: 2,
    borderWidth: 1,
    color: "#F7F2EC",
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
    backgroundColor: "rgba(201, 169, 110, 0.08)",
    borderColor: "rgba(201, 169, 110, 0.34)",
    borderRadius: 1,
    borderWidth: 1,
    minHeight: 50,
    justifyContent: "center",
  },
  googleButton: {
    alignItems: "center",
    backgroundColor: "rgba(201, 169, 110, 0.04)",
    borderColor: "rgba(201, 169, 110, 0.24)",
    borderRadius: 1,
    borderWidth: 1,
    minHeight: 46,
    justifyContent: "center",
  },
  googleButtonText: {
    color: "#F7F2EC",
    fontSize: 10,
    fontWeight: "500",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  primaryButtonText: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 16,
    fontStyle: "italic",
    fontWeight: "300",
    letterSpacing: 2,
  },
  ghostButton: {
    alignItems: "center",
    backgroundColor: "rgba(201, 169, 110, 0.04)",
    borderColor: "rgba(201, 169, 110, 0.22)",
    borderRadius: 1,
    borderWidth: 1,
    minHeight: 42,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  ghostButtonText: {
    color: "#C9A96E",
    fontSize: 10,
    fontWeight: "500",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  listItem: {
    backgroundColor: "rgba(20, 12, 4, 0.62)",
    borderColor: "rgba(201, 169, 110, 0.16)",
    borderRadius: 2,
    borderWidth: 1,
    gap: 6,
    padding: 14,
  },
  listDate: {
    color: "#F7F2EC",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 17,
    fontStyle: "italic",
    fontWeight: "300",
  },
  listMeta: {
    color: "rgba(247, 242, 236, 0.62)",
    fontSize: 14,
  },
  chips: {
    color: "#C9A96E",
    fontSize: 12,
    fontWeight: "500",
  },
  empty: {
    color: "rgba(247, 242, 236, 0.56)",
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
    backgroundColor: "rgba(20, 12, 4, 0.62)",
    borderColor: "rgba(201, 169, 110, 0.16)",
    borderRadius: 2,
    borderWidth: 1,
    flexBasis: "30%",
    flexGrow: 1,
    minHeight: 62,
    justifyContent: "center",
  },
  overviewTitle: {
    color: "rgba(201, 169, 110, 0.52)",
    fontSize: 12,
    fontWeight: "500",
    letterSpacing: 1,
  },
  overviewCount: {
    color: "#F7F2EC",
    fontSize: 20,
    fontWeight: "500",
  },
  markdown: {
    backgroundColor: "rgba(20, 12, 4, 0.62)",
    borderColor: "rgba(201, 169, 110, 0.16)",
    borderRadius: 2,
    borderWidth: 1,
    color: "#F7F2EC",
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
    color: "#C4836A",
    fontSize: 13,
    fontWeight: "500",
  },
  resultLine: {
    color: "rgba(247, 242, 236, 0.72)",
    fontSize: 14,
    lineHeight: 20,
  },
});

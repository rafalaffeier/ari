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
type TranslationLanguage = "en" | "ru" | "uk" | "es" | "de" | "it" | "pt";
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
    continueGoogle: "Continue with Google",
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
    continueGoogle: "Continuar con Google",
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
  ru: {
    accessLight: "Откройте свой свет",
    add: "Добавить",
    addEntry: "Добавить запись",
    alignMe: "Войти ->",
    create: "Создать",
    createAccount: "Создание аккаунта",
    createLight: "Создать свет ->",
    day: "День",
    emailPasswordRequired: "Email и пароль обязательны.",
    entries: "записей",
    exit: "Выйти",
    googleActive: "Сессия Google активна",
    continueGoogle: "Продолжить с Google",
    googleCodePlaceholder: "Вставьте код ARI Google",
    googleMissingCode: "Сначала вставьте код входа ARI Google.",
    googleMissingTitle: "Нет кода",
    googleOpen: "Открываю Google",
    googleOpenError: "Не удалось открыть Google",
    googlePaste: "Вставьте код ARI из браузера",
    googleVerify: "Проверить Google",
    googleVerifying: "Проверка Google",
    language: "Язык",
    load: "Загрузить",
    login: "Войти",
    missingLogin: "Нет данных входа",
    noCache: "Нет сохраненной копии этого дня",
    noDays: "Дней пока нет.",
    noResults: "Нет результатов.",
    offlineCache: "Офлайн-кэш",
    password: "пароль",
    query: "запрос",
    queued: "В очереди",
    ready: "Готово",
    saveEntry: "Сохранить запись",
    search: "Поиск",
    searchSynced: "Поиск синхронизирован",
    selectLanguage: "Язык",
    signedOut: "Сессия закрыта",
    signingIn: "Вход",
    sync: "Синхронизировать",
    synced: "Синхронизировано",
    timeline: "Лента",
    timelineSynced: "Лента синхронизирована",
    unableSignIn: "Не удалось войти",
    unableVerifyGoogle: "Не удалось проверить Google",
    working: "Работаю...",
    writeMemory: "Напишите запись памяти",
  },
  uk: {
    accessLight: "Відкрийте своє світло",
    add: "Додати",
    addEntry: "Додати запис",
    alignMe: "Увійти ->",
    create: "Створити",
    createAccount: "Створення акаунта",
    createLight: "Створити світло ->",
    day: "День",
    emailPasswordRequired: "Email і пароль обов'язкові.",
    entries: "записів",
    exit: "Вийти",
    googleActive: "Сесія Google активна",
    continueGoogle: "Продовжити з Google",
    googleCodePlaceholder: "Вставте код ARI Google",
    googleMissingCode: "Спочатку вставте код входу ARI Google.",
    googleMissingTitle: "Немає коду",
    googleOpen: "Відкриваю Google",
    googleOpenError: "Не вдалося відкрити Google",
    googlePaste: "Вставте код ARI з браузера",
    googleVerify: "Перевірити Google",
    googleVerifying: "Перевірка Google",
    language: "Мова",
    load: "Завантажити",
    login: "Увійти",
    missingLogin: "Немає даних входу",
    noCache: "Немає збереженої копії цього дня",
    noDays: "Днів поки немає.",
    noResults: "Немає результатів.",
    offlineCache: "Офлайн-кеш",
    password: "пароль",
    query: "запит",
    queued: "У черзі",
    ready: "Готово",
    saveEntry: "Зберегти запис",
    search: "Пошук",
    searchSynced: "Пошук синхронізовано",
    selectLanguage: "Мова",
    signedOut: "Сесію закрито",
    signingIn: "Вхід",
    sync: "Синхронізувати",
    synced: "Синхронізовано",
    timeline: "Стрічка",
    timelineSynced: "Стрічку синхронізовано",
    unableSignIn: "Не вдалося увійти",
    unableVerifyGoogle: "Не вдалося перевірити Google",
    working: "Працюю...",
    writeMemory: "Напишіть запис пам'яті",
  },
  de: {
    accessLight: "Greife auf dein Licht zu",
    add: "Hinzufügen",
    addEntry: "Eintrag hinzufügen",
    alignMe: "Einloggen ->",
    create: "Erstellen",
    createAccount: "Konto wird erstellt",
    createLight: "Licht erstellen ->",
    day: "Tag",
    emailPasswordRequired: "E-Mail und Passwort sind erforderlich.",
    entries: "Einträge",
    exit: "Beenden",
    googleActive: "Google-Sitzung aktiv",
    continueGoogle: "Mit Google fortfahren",
    googleCodePlaceholder: "ARI-Google-Code einfügen",
    googleMissingCode: "Füge zuerst den ARI-Google-Anmeldecode ein.",
    googleMissingTitle: "Code fehlt",
    googleOpen: "Google wird geöffnet",
    googleOpenError: "Google konnte nicht geöffnet werden",
    googlePaste: "Füge den ARI-Code aus deinem Browser ein",
    googleVerify: "Google prüfen",
    googleVerifying: "Google wird geprüft",
    language: "Sprache",
    load: "Laden",
    login: "Login",
    missingLogin: "Login fehlt",
    noCache: "Keine gespeicherte Kopie für diesen Tag",
    noDays: "Noch keine Tage.",
    noResults: "Keine Ergebnisse.",
    offlineCache: "Offline-Cache",
    password: "Passwort",
    query: "Suche",
    queued: "In Warteschlange",
    ready: "Bereit",
    saveEntry: "Eintrag speichern",
    search: "Suchen",
    searchSynced: "Suche synchronisiert",
    selectLanguage: "Sprache",
    signedOut: "Abgemeldet",
    signingIn: "Anmeldung",
    sync: "Synchronisieren",
    synced: "Synchronisiert",
    timeline: "Zeitleiste",
    timelineSynced: "Zeitleiste synchronisiert",
    unableSignIn: "Anmeldung nicht möglich",
    unableVerifyGoogle: "Google konnte nicht geprüft werden",
    working: "Arbeite...",
    writeMemory: "Schreibe einen Erinnerungseintrag",
  },
  it: {
    accessLight: "Accedi alla tua luce",
    add: "Aggiungi",
    addEntry: "Aggiungi voce",
    alignMe: "Entra ->",
    create: "Crea",
    createAccount: "Creazione account",
    createLight: "Crea luce ->",
    day: "Giorno",
    emailPasswordRequired: "Email e password sono obbligatorie.",
    entries: "voci",
    exit: "Esci",
    googleActive: "Sessione Google attiva",
    continueGoogle: "Continua con Google",
    googleCodePlaceholder: "Incolla il codice Google di ARI",
    googleMissingCode: "Incolla prima il codice di accesso Google di ARI.",
    googleMissingTitle: "Codice mancante",
    googleOpen: "Apro Google",
    googleOpenError: "Impossibile aprire Google",
    googlePaste: "Incolla il codice ARI dal browser",
    googleVerify: "Verifica Google",
    googleVerifying: "Verifica Google",
    language: "Lingua",
    load: "Carica",
    login: "Accesso",
    missingLogin: "Accesso mancante",
    noCache: "Nessuna copia salvata per questo giorno",
    noDays: "Ancora nessun giorno.",
    noResults: "Nessun risultato.",
    offlineCache: "Cache offline",
    password: "password",
    query: "ricerca",
    queued: "In coda",
    ready: "Pronto",
    saveEntry: "Salva voce",
    search: "Cerca",
    searchSynced: "Ricerca sincronizzata",
    selectLanguage: "Lingua",
    signedOut: "Sessione chiusa",
    signingIn: "Accesso in corso",
    sync: "Sincronizza",
    synced: "Sincronizzato",
    timeline: "Cronologia",
    timelineSynced: "Cronologia sincronizzata",
    unableSignIn: "Impossibile accedere",
    unableVerifyGoogle: "Impossibile verificare Google",
    working: "Lavoro...",
    writeMemory: "Scrivi una voce di memoria",
  },
  pt: {
    accessLight: "Acesse sua luz",
    add: "Adicionar",
    addEntry: "Adicionar entrada",
    alignMe: "Entrar ->",
    create: "Criar",
    createAccount: "Criando conta",
    createLight: "Criar luz ->",
    day: "Dia",
    emailPasswordRequired: "Email e senha são obrigatórios.",
    entries: "entradas",
    exit: "Sair",
    googleActive: "Sessão do Google ativa",
    continueGoogle: "Continuar com Google",
    googleCodePlaceholder: "Cole o código Google da ARI",
    googleMissingCode: "Cole primeiro o código de login Google da ARI.",
    googleMissingTitle: "Código ausente",
    googleOpen: "Abrindo Google",
    googleOpenError: "Não foi possível abrir o Google",
    googlePaste: "Cole o código ARI do seu navegador",
    googleVerify: "Verificar Google",
    googleVerifying: "Verificando Google",
    language: "Idioma",
    load: "Carregar",
    login: "Entrar",
    missingLogin: "Login ausente",
    noCache: "Não há cópia salva para este dia",
    noDays: "Ainda não há dias.",
    noResults: "Sem resultados.",
    offlineCache: "Cache offline",
    password: "senha",
    query: "consulta",
    queued: "Na fila",
    ready: "Pronto",
    saveEntry: "Salvar entrada",
    search: "Buscar",
    searchSynced: "Busca sincronizada",
    selectLanguage: "Idioma",
    signedOut: "Sessão encerrada",
    signingIn: "Entrando",
    sync: "Sincronizar",
    synced: "Sincronizado",
    timeline: "Linha do tempo",
    timelineSynced: "Linha do tempo sincronizada",
    unableSignIn: "Não foi possível entrar",
    unableVerifyGoogle: "Não foi possível verificar Google",
    working: "Trabalhando...",
    writeMemory: "Escreva uma entrada de memória",
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
  ru: { tasks: "Задачи", decisions: "Решения", pending: "Ожидает", facts: "Факты", chat: "Чат", technical_events: "Тех" },
  uk: { tasks: "Завдання", decisions: "Рішення", pending: "Очікує", facts: "Факти", chat: "Чат", technical_events: "Тех" },
  de: { tasks: "Aufgaben", decisions: "Entscheidungen", pending: "Offen", facts: "Fakten", chat: "Chat", technical_events: "Tech" },
  it: { tasks: "Attività", decisions: "Decisioni", pending: "In sospeso", facts: "Fatti", chat: "Chat", technical_events: "Tech" },
  pt: { tasks: "Tarefas", decisions: "Decisões", pending: "Pendente", facts: "Fatos", chat: "Chat", technical_events: "Técnico" },
};

const STATUS_TEXT: Record<TranslationLanguage, { entrySaved: string; entryQueued: string }> = {
  en: { entrySaved: "Entry saved", entryQueued: "Entry queued offline" },
  ru: { entrySaved: "Запись сохранена", entryQueued: "Запись добавлена в офлайн-очередь" },
  uk: { entrySaved: "Запис збережено", entryQueued: "Запис додано в офлайн-чергу" },
  es: { entrySaved: "Entrada guardada", entryQueued: "Entrada en cola sin conexion" },
  de: { entrySaved: "Eintrag gespeichert", entryQueued: "Eintrag offline vorgemerkt" },
  it: { entrySaved: "Voce salvata", entryQueued: "Voce in coda offline" },
  pt: { entrySaved: "Entrada salva", entryQueued: "Entrada na fila offline" },
};

function normalizeLanguage(value?: string | null): AppLanguage {
  return (value || "en").toLowerCase().replace("_", "-").split("-")[0] || "en";
}

function translationLanguage(value?: string | null): TranslationLanguage {
  const language = normalizeLanguage(value);
  return language in STRINGS ? (language as TranslationLanguage) : "en";
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
  const [mode, setMode] = useState<"login" | "register" | "forgot" | "reset">("login");
  const [resetToken, setResetToken] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
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
  const authText = {
    forgotPassword: uiLanguage === "es" ? "Olvidaste tu contrasena?" : "Forgot password?",
    sendRecovery: uiLanguage === "es" ? "Enviar recuperacion ->" : "Send recovery ->",
    resetPassword: uiLanguage === "es" ? "Cambiar contrasena ->" : "Change password ->",
    recoveryStatus: uiLanguage === "es" ? "Enviando recuperacion" : "Sending recovery",
    recoveryReady: uiLanguage === "es" ? "Recuperacion lista" : "Recovery ready",
    pasteRecovery: uiLanguage === "es" ? "Pega el enlace o codigo de recuperacion" : "Paste recovery link or code",
    recoverySent: uiLanguage === "es" ? "Revisa tu email y pega el enlace" : "Check email and paste the link",
    changingPassword: uiLanguage === "es" ? "Cambiando contrasena" : "Changing password",
    passwordUpdated: uiLanguage === "es" ? "Contrasena actualizada" : "Password updated",
    showPassword: uiLanguage === "es" ? "Mostrar contrasena" : "Show password",
    hidePassword: uiLanguage === "es" ? "Ocultar contrasena" : "Hide password",
  };
  const sections = useMemo(
    () => SECTIONS.map((item) => ({ ...item, label: SECTION_LABELS[uiLanguage][item.key] })),
    [uiLanguage],
  );

  const signedIn = Boolean(token && workspaceId);

  useEffect(() => {
    memoryCache.loadSession().then((session) => {
      if (session) setSession(session.token, session.userId, session.workspaceId);
    });
    memoryCache.loadPendingEntries().then(setPendingEntries);
  }, [setSession]);

  function changeLanguage(nextLanguage: AppLanguage) {
    setLanguage(nextLanguage);
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

  function recoveryTokenValue(value: string) {
    const trimmed = value.trim();
    const marker = "reset_token=";
    if (trimmed.includes(marker)) return trimmed.split(marker).pop()?.split(/[&#]/)[0] ?? trimmed;
    return trimmed;
  }

  async function requestPasswordRecovery() {
    if (!email.trim()) {
      Alert.alert(t.missingLogin, "Email is required.");
      return;
    }
    setIsBusy(true);
    setStatus(authText.recoveryStatus);
    try {
      const recovery = await api.forgotPassword(email.trim());
      if (recovery.reset_url) setResetToken(recovery.reset_url);
      setMode("reset");
      setStatus(recovery.reset_url ? authText.recoveryReady : authText.recoverySent);
    } catch (error) {
      setIsOffline(true);
      setStatus(error instanceof Error ? error.message : t.unableSignIn);
    } finally {
      setIsBusy(false);
    }
  }

  async function submitPasswordReset() {
    const tokenValue = recoveryTokenValue(resetToken);
    if (!tokenValue || !password) {
      Alert.alert(t.missingLogin, "Recovery code and password are required.");
      return;
    }
    setIsBusy(true);
    setStatus(authText.changingPassword);
    try {
      await api.resetPassword(tokenValue, password);
      setPassword("");
      setResetToken("");
      setMode("login");
      setStatus(authText.passwordUpdated);
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
      setStatus(STATUS_TEXT[uiLanguage].entrySaved);
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
      setStatus(STATUS_TEXT[uiLanguage].entryQueued);
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
        <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.authKeyboard}>
          <ScrollView
            contentContainerStyle={styles.authScroll}
            keyboardShouldPersistTaps="handled"
            showsVerticalScrollIndicator={false}
          >
            <View style={styles.authCard}>
              <Text style={styles.sunMark}>☉</Text>
              <Text style={styles.brand}>Ari</Text>
              <Text style={styles.brandSub}>Solara · Quantum Intelligent</Text>
              <Text style={styles.authTitle}>{t.accessLight}</Text>
              <View style={[styles.segment, styles.authSegment]}>
                <SegmentButton active={mode === "login"} label={t.login} onPress={() => setMode("login")} />
                <SegmentButton active={mode === "register"} label={t.create} onPress={() => setMode("register")} />
              </View>
              {mode !== "reset" && (
                <TextInput
                  autoCapitalize="none"
                  keyboardType="email-address"
                  onChangeText={setEmail}
                  placeholder="soul@ari.ai"
                  placeholderTextColor="rgba(201,169,110,0.34)"
                  style={styles.input}
                  value={email}
                />
              )}
              {mode === "reset" && (
                <TextInput
                  autoCapitalize="none"
                  onChangeText={setResetToken}
                  placeholder={authText.pasteRecovery}
                  placeholderTextColor="rgba(201,169,110,0.34)"
                  style={styles.input}
                  value={resetToken}
                />
              )}
              {mode !== "forgot" && (
                <View style={styles.passwordRow}>
                  <TextInput
                    onChangeText={setPassword}
                    placeholder={t.password}
                    placeholderTextColor="rgba(201,169,110,0.34)"
                    secureTextEntry={!passwordVisible}
                    style={styles.passwordInput}
                    value={password}
                  />
                  <Pressable
                    accessibilityLabel={passwordVisible ? authText.hidePassword : authText.showPassword}
                    accessibilityRole="button"
                    onPress={() => setPasswordVisible((visible) => !visible)}
                    style={styles.passwordToggle}
                  >
                    <Text style={styles.passwordToggleText}>{passwordVisible ? "◌" : "◉"}</Text>
                  </Pressable>
                </View>
              )}
              {mode === "login" && (
                <>
                  <Pressable disabled={isBusy} onPress={openGoogleLogin} style={styles.googleButton}>
                    <Text style={styles.googleButtonText}>{t.continueGoogle}</Text>
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
              <Pressable
                disabled={isBusy}
                onPress={mode === "forgot" ? requestPasswordRecovery : mode === "reset" ? submitPasswordReset : authenticate}
                style={styles.primaryButton}
              >
                <Text style={styles.primaryButtonText}>
                  {isBusy
                    ? t.working
                    : mode === "login"
                      ? t.alignMe
                      : mode === "register"
                        ? t.createLight
                        : mode === "forgot"
                          ? authText.sendRecovery
                          : authText.resetPassword}
                </Text>
              </Pressable>
              {mode === "login" && (
                <Pressable disabled={isBusy} onPress={() => setMode("forgot")} style={styles.textButton}>
                  <Text style={styles.textButtonText}>{authText.forgotPassword}</Text>
                </Pressable>
              )}
              {(mode === "forgot" || mode === "reset") && (
                <Pressable disabled={isBusy} onPress={() => setMode("login")} style={styles.textButton}>
                  <Text style={styles.textButtonText}>{t.login}</Text>
                </Pressable>
              )}
              <StatusLine isBusy={isBusy} isOffline={isOffline} offlineLabel={t.offlineCache} status={status} />
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.screen}>
      <View style={styles.header}>
        <View style={styles.headerIdentity}>
          <Text style={styles.brandSmall}>Consulta activa</Text>
          <Text style={styles.meta}>ARI · Voz desactivada</Text>
        </View>
        <Pressable onPress={signOut} style={styles.headerButton}>
          <Text style={styles.headerButtonText}>⋮</Text>
        </Pressable>
      </View>

      <View style={[styles.segment, styles.mainSegment]}>
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
      {isBusy && <ActivityIndicator size="small" color="#D99A3D" />}
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
    backgroundColor: "#0B0805",
  },
  auth: {
    flex: 1,
    justifyContent: "center",
    padding: 22,
  },
  authKeyboard: {
    flex: 1,
  },
  authScroll: {
    flexGrow: 1,
    justifyContent: "center",
    paddingHorizontal: 18,
    paddingVertical: 22,
  },
  authCard: {
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 24,
    borderWidth: 1,
    gap: 14,
    paddingHorizontal: 28,
    paddingVertical: 34,
  },
  sunMark: {
    color: "#D99A3D",
    fontSize: 32,
    textAlign: "center",
  },
  header: {
    alignItems: "flex-start",
    backgroundColor: "#0B0805",
    borderBottomColor: "rgba(217, 154, 61, 0.12)",
    borderBottomWidth: 0,
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 14,
    minHeight: 96,
    paddingHorizontal: 20,
    paddingBottom: 18,
    paddingTop: 24,
  },
  headerIdentity: {
    flex: 1,
    minWidth: 0,
  },
  headerButton: {
    alignItems: "center",
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 14,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 48,
    paddingHorizontal: 0,
  },
  headerButtonText: {
    color: "rgba(255, 248, 240, 0.8)",
    fontSize: 26,
    lineHeight: 28,
  },
  brand: {
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Inter", android: "sans-serif", default: "system-ui" }),
    fontSize: 44,
    fontStyle: "italic",
    fontWeight: "300",
    letterSpacing: 6,
    textAlign: "center",
  },
  brandSub: {
    color: "#A89A88",
    fontSize: 8,
    letterSpacing: 4,
    marginBottom: 10,
    marginTop: 7,
    textAlign: "center",
    textTransform: "uppercase",
  },
  authTitle: {
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 21,
    fontStyle: "italic",
    fontWeight: "300",
    marginBottom: 2,
    textAlign: "center",
  },
  brandSmall: {
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Inter", android: "sans-serif", default: "system-ui" }),
    fontSize: 28,
    fontWeight: "400",
    letterSpacing: 0,
  },
  meta: {
    alignSelf: "flex-start",
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 999,
    borderWidth: 1,
    color: "#A89A88",
    fontSize: 12,
    letterSpacing: 0,
    marginTop: 10,
    overflow: "hidden",
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  segment: {
    backgroundColor: "transparent",
    borderColor: "transparent",
    borderRadius: 0,
    borderWidth: 0,
    flexDirection: "row",
    gap: 10,
    marginBottom: 6,
    padding: 0,
  },
  authSegment: {
    marginBottom: 4,
  },
  mainSegment: {
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.18)",
    borderRadius: 18,
    borderWidth: 1,
    marginHorizontal: 20,
    marginTop: 4,
    padding: 5,
  },
  segmentButton: {
    alignItems: "center",
    borderColor: "transparent",
    borderRadius: 14,
    borderWidth: 1,
    flex: 1,
    minHeight: 40,
    justifyContent: "center",
    paddingHorizontal: 8,
  },
  segmentButtonActive: {
    backgroundColor: "rgba(217, 154, 61, 0.22)",
    borderColor: "rgba(217, 154, 61, 0.28)",
  },
  segmentText: {
    color: "#6F604D",
    fontSize: 8,
    fontWeight: "500",
    letterSpacing: 3,
    textTransform: "uppercase",
  },
  segmentTextActive: {
    color: "#F4EFE7",
  },
  status: {
    alignItems: "center",
    flexDirection: "row",
    gap: 8,
    minHeight: 30,
    backgroundColor: "#0B0805",
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  statusDot: {
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  statusDotOnline: {
    backgroundColor: "#D99A3D",
  },
  statusDotOffline: {
    backgroundColor: "#C4836A",
  },
  statusText: {
    color: "#A89A88",
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
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 190,
  },
  panel: {
    backgroundColor: "#1A120B",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 24,
    borderWidth: 1,
    gap: 12,
    padding: 18,
  },
  title: {
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Inter", android: "sans-serif", default: "system-ui" }),
    fontSize: 25,
    fontStyle: "normal",
    fontWeight: "300",
  },
  rowBetween: {
    alignItems: "center",
    flexDirection: "row",
    gap: 10,
    justifyContent: "space-between",
  },
  input: {
    backgroundColor: "#120D08",
    borderBottomWidth: 0,
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 16,
    borderWidth: 1,
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Inter", android: "sans-serif", default: "system-ui" }),
    fontSize: 18,
    fontStyle: "italic",
    minHeight: 64,
    paddingHorizontal: 14,
  },
  passwordRow: {
    alignItems: "center",
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 16,
    borderWidth: 1,
    flexDirection: "row",
    minHeight: 64,
  },
  passwordInput: {
    color: "#F4EFE7",
    flex: 1,
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 18,
    fontStyle: "italic",
    minHeight: 64,
    paddingHorizontal: 14,
  },
  passwordToggle: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 44,
    width: 40,
  },
  passwordToggleText: {
    color: "#F0B85A",
    fontSize: 18,
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
    backgroundColor: "#D99A3D",
    borderColor: "transparent",
    borderRadius: 999,
    borderWidth: 0,
    marginTop: 8,
    minHeight: 64,
    justifyContent: "center",
  },
  googleButton: {
    alignItems: "center",
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 16,
    borderWidth: 1,
    minHeight: 56,
    justifyContent: "center",
  },
  googleButtonText: {
    color: "#F4EFE7",
    fontSize: 9,
    fontWeight: "500",
    letterSpacing: 3,
    textTransform: "uppercase",
  },
  primaryButtonText: {
    color: "#0B0805",
    fontFamily: Platform.select({ ios: "Inter", android: "sans-serif", default: "system-ui" }),
    fontSize: 16,
    fontStyle: "italic",
    fontWeight: "300",
    letterSpacing: 3,
  },
  ghostButton: {
    alignItems: "center",
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 14,
    borderWidth: 1,
    minHeight: 42,
    justifyContent: "center",
    paddingHorizontal: 14,
  },
  ghostButtonText: {
    color: "#F0B85A",
    fontSize: 10,
    fontWeight: "500",
    letterSpacing: 2,
    textTransform: "uppercase",
  },
  textButton: {
    alignItems: "center",
    justifyContent: "center",
    minHeight: 34,
  },
  textButtonText: {
    color: "rgba(201, 169, 110, 0.72)",
    fontSize: 11,
    letterSpacing: 1,
    textDecorationLine: "underline",
    textTransform: "uppercase",
  },
  listItem: {
    backgroundColor: "#120D08",
    borderColor: "rgba(217, 154, 61, 0.28)",
    borderRadius: 18,
    borderWidth: 1,
    gap: 6,
    minHeight: 128,
    padding: 16,
  },
  listDate: {
    color: "#F4EFE7",
    fontFamily: Platform.select({ ios: "Georgia", android: "serif", default: "serif" }),
    fontSize: 17,
    fontStyle: "italic",
    fontWeight: "300",
  },
  listMeta: {
    color: "#A89A88",
    fontSize: 14,
  },
  chips: {
    color: "#F0B85A",
    fontSize: 12,
    fontWeight: "500",
  },
  empty: {
    color: "#6F604D",
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

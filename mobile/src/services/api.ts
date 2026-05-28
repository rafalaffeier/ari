const BASE_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user_id: string;
  default_workspace_id: string | null;
  email?: string | null;
};

export type PasswordRecoveryResponse = {
  detail: string;
  reset_url?: string | null;
};

export type Workspace = {
  id: string;
  name: string;
};

export type TimelineDay = {
  date: string;
  path: string;
  entry_count: number;
  sections: Record<string, number>;
};

export type JournalDay = {
  workspace_id: string;
  date: string;
  content: string;
};

export type JournalOverview = {
  workspace_id: string;
  date: string;
  sections: Record<string, string[]>;
};

export type SearchResult = {
  date: string;
  path: string;
  line_number: number;
  line: string;
};

export type JournalSection = "tasks" | "decisions" | "pending" | "facts" | "chat" | "technical_events";

export type ConversationMessage = {
  role: "user" | "assistant" | string;
  content: string;
};

export type ThreadSummary = {
  id: string;
  title: string;
  date: string;
  path: string;
  updated_at: string;
  message_count: number;
};

export type ThreadDetail = ThreadSummary & {
  created_at: string;
  messages: ConversationMessage[];
};

export type ChatResponse = {
  reply: string;
  model: string;
  memory_results: unknown[];
  stored: boolean;
  stored_actions: string[];
  thread_id?: string | null;
};

export type GoogleIntegrationStatus = {
  connected: boolean;
  provider: string;
  scopes: string[];
  status: string;
  expires_at?: string | null;
};

export type GoogleIntegrationStartResponse = {
  authorization_url: string;
  scopes: string[];
};

export type GoogleDriveFileMetadata = {
  id: string;
  name: string;
  mimeType?: string | null;
  webViewLink?: string | null;
  modifiedTime?: string | null;
  owners: string[];
};

export type GoogleDriveSearchResponse = {
  files: GoogleDriveFileMetadata[];
  nextPageToken?: string | null;
};

export type GmailMessageSummary = {
  id: string;
  threadId: string;
  snippet?: string | null;
  subject?: string | null;
  from_email?: string | null;
  to?: string | null;
  date?: string | null;
  internalDate?: string | null;
  labelIds?: string[];
};

export type GmailSearchResponse = {
  messages: GmailMessageSummary[];
  nextPageToken?: string | null;
  resultSizeEstimate?: number | null;
};

export type GmailThreadMessage = GmailMessageSummary & {
  text?: string | null;
};

export type GmailThreadResponse = {
  id: string;
  messages: GmailThreadMessage[];
};

export type ActionResponse = {
  id: string;
  workspace_id: string;
  user_id: string;
  device_id?: string | null;
  tool_name: string;
  tool_version: string;
  params: Record<string, unknown>;
  status: string;
  risk_level: string;
  requires_confirmation: boolean;
  confirmation_token?: string | null;
  confirmed_at?: string | null;
  result?: Record<string, unknown> | null;
  created_at: string;
};

type RequestOptions = RequestInit & {
  token?: string | null;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (body.detail) {
        detail = `: ${typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail)}`;
      }
    } catch {
      detail = "";
    }
    throw new Error(`API error ${res.status}${detail}`);
  }
  return res.json();
}

export const api = {
  googleAuthUrl: (client: "web" | "desktop" | "mobile" = "mobile") =>
    `${BASE_URL}/auth/google/start?client=${encodeURIComponent(client)}`,
  exchangeGoogleCode: (code: string) =>
    request<AuthResponse>("/auth/google/exchange", {
      method: "POST",
      body: JSON.stringify({ code }),
    }),
  getGoogleIntegrationStatus: (token: string) =>
    request<GoogleIntegrationStatus>("/integrations/google/status", { token }),
  startGoogleIntegration: (token: string, client: "web" | "desktop" | "mobile" = "mobile", returnTo = "/") =>
    request<GoogleIntegrationStartResponse>("/integrations/google/start", {
      method: "POST",
      token,
      body: JSON.stringify({ client, return_to: returnTo }),
    }),
  searchGoogleDriveFiles: (token: string, query = "", pageSize = 10) =>
    request<GoogleDriveSearchResponse>(
      `/integrations/google/drive/files?q=${encodeURIComponent(query)}&page_size=${encodeURIComponent(String(pageSize))}`,
      { token },
    ),
  searchGmailMessages: (token: string, query = "", maxResults = 10) =>
    request<GmailSearchResponse>(
      `/integrations/google/gmail/messages?q=${encodeURIComponent(query)}&max_results=${encodeURIComponent(String(maxResults))}`,
      { token },
    ),
  readGmailThread: (token: string, threadId: string) =>
    request<GmailThreadResponse>(`/integrations/google/gmail/threads/${encodeURIComponent(threadId)}`, { token }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/auth/login", {
      method: "POST",
      body: new URLSearchParams({ username: email, password }).toString(),
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
    }),
  register: (email: string, password: string) =>
    request<AuthResponse>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),
  forgotPassword: (email: string) =>
    request<PasswordRecoveryResponse>("/auth/forgot-password", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  resetPassword: (token: string, password: string) =>
    request<PasswordRecoveryResponse>("/auth/reset-password", {
      method: "POST",
      body: JSON.stringify({ token, password }),
    }),
  getWorkspaces: (token: string) => request<Workspace[]>("/workspaces/", { token }),
  getActions: (token: string, workspaceId: string, includeConfirmationTokens = false, limit = 50) =>
    request<ActionResponse[]>(
      `/actions/${workspaceId}?limit=${limit}&include_confirmation_tokens=${includeConfirmationTokens ? "true" : "false"}`,
      { token },
    ),
  confirmAction: (token: string, workspaceId: string, actionId: string, confirmationToken: string) =>
    request<ActionResponse>(`/actions/${workspaceId}/${encodeURIComponent(actionId)}/confirm`, {
      method: "POST",
      token,
      body: JSON.stringify({ confirmation_token: confirmationToken }),
    }),
  rejectAction: (token: string, workspaceId: string, actionId: string) =>
    request<ActionResponse>(`/actions/${workspaceId}/${encodeURIComponent(actionId)}/reject`, {
      method: "POST",
      token,
    }),
  getTimeline: (token: string, workspaceId: string, limit = 30) =>
    request<TimelineDay[]>(`/memory/${workspaceId}/timeline?limit=${limit}`, { token }),
  getJournalDay: (token: string, workspaceId: string, day: string) =>
    request<JournalDay>(`/memory/${workspaceId}/journal/${day}`, { token }),
  getJournalOverview: (token: string, workspaceId: string, day: string) =>
    request<JournalOverview>(`/memory/${workspaceId}/journal/${day}/overview`, { token }),
  addJournalEntry: (token: string, workspaceId: string, day: string, section: JournalSection, text: string) =>
    request<{ workspace_id: string; date: string; path: string }>(`/memory/${workspaceId}/journal/${day}/entries`, {
      method: "POST",
      token,
      body: JSON.stringify({ section, text }),
    }),
  searchMemory: (token: string, workspaceId: string, query: string, limit = 25) =>
    request<SearchResult[]>(
      `/memory/${workspaceId}/search?q=${encodeURIComponent(query)}&limit=${limit}`,
      { token },
    ),
  listThreads: (token: string, workspaceId: string, limit = 30) =>
    request<ThreadSummary[]>(`/messages/${workspaceId}/threads?limit=${limit}`, { token }),
  createThread: (token: string, workspaceId: string, title?: string | null) =>
    request<ThreadDetail>(`/messages/${workspaceId}/threads`, {
      method: "POST",
      token,
      body: JSON.stringify({ title: title ?? null }),
    }),
  readThread: (token: string, workspaceId: string, threadId: string) =>
    request<ThreadDetail>(`/messages/${workspaceId}/threads/${encodeURIComponent(threadId)}`, { token }),
  chat: (token: string, workspaceId: string, message: string, threadId?: string | null) =>
    request<ChatResponse>(`/messages/${workspaceId}/chat`, {
      method: "POST",
      token,
      body: JSON.stringify({
        message,
        thread_id: threadId || null,
        use_memory: true,
        memory_limit: 8,
      }),
    }),
};

pub mod agent;
pub mod memory;
pub mod permissions;
pub mod storage;
pub mod tools;

use base64::engine::general_purpose::STANDARD as BASE64_STANDARD;
use base64::Engine as _;
use chrono::Utc;
use memory::client::{
    ActionResponse, AuditEventResponse, AuthResponse, ChatResponse, Conversation,
    JournalDayResponse, JournalEntryResponse, JournalOverviewResponse, MemoryClient,
    MemoryClientError, OrchestrateResponse, PasswordRecoveryResponse, RecentMessage, SearchResult,
    SpeechResponse, Thread, ThreadSummary, VoiceResponse,
};
use memory::crypto::WorkspaceKey;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::Command;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{Manager, State};
use tokio::sync::RwLock;

const CONFIG_FILE_NAME: &str = "desktop-config.json";
const PRODUCTION_BACKEND_URL: &str = "https://ari.flusscreative.com";

// Persistent desktop settings live in the app config directory. Secrets stay in
// secure storage and are referenced here only by logical name.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopConfig {
    pub backend_url: String,
    pub default_workspace_id: String,
    pub local_memory_root: PathBuf,
}

#[derive(Debug, Default)]
pub struct AppState {
    // Cached after login/config load so commands do not hit disk/keychain on
    // every call. The keychain remains the source of truth across restarts.
    config: Arc<RwLock<Option<DesktopConfig>>>,
    access_token: Arc<RwLock<Option<String>>>,
}

#[derive(Debug, Serialize)]
pub struct DesktopError {
    message: String,
    kind: &'static str,
}

impl DesktopError {
    fn configuration(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            kind: "configuration",
        }
    }

    fn storage(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            kind: "storage",
        }
    }

    fn auth(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            kind: "auth",
        }
    }

    fn tool(message: impl Into<String>) -> Self {
        Self {
            message: message.into(),
            kind: "tool",
        }
    }
}

impl From<MemoryClientError> for DesktopError {
    fn from(value: MemoryClientError) -> Self {
        Self {
            message: value.to_string(),
            kind: value.kind(),
        }
    }
}

#[derive(Debug, Serialize)]
pub struct ConfigurationResponse {
    pub backend_url: String,
    pub default_workspace_id: String,
    pub local_memory_root: PathBuf,
}

#[derive(Debug, Serialize)]
pub struct WorkspaceKeyStatus {
    pub workspace_id: String,
    pub key_id: String,
    pub created: bool,
}

#[tauri::command]
fn default_backend_url() -> String {
    std::env::var("AI_ASSISTANT_BACKEND_URL")
        .ok()
        .map(|value| value.trim().trim_end_matches('/').to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| PRODUCTION_BACKEND_URL.to_string())
}

#[tauri::command]
async fn configure_desktop(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    backend_url: String,
    access_token: String,
    default_workspace_id: String,
    local_memory_root: String,
) -> Result<ConfigurationResponse, DesktopError> {
    if access_token.trim().is_empty() {
        return Err(DesktopError::configuration("access_token cannot be empty"));
    }

    let config = build_config(backend_url, default_workspace_id, local_memory_root)?;
    save_desktop_config(&app, &config)?;
    storage::store_token("access_token", &access_token).map_err(|error| {
        DesktopError::storage(format!("failed to store access token securely: {error}"))
    })?;

    *state.config.write().await = Some(config.clone());
    *state.access_token.write().await = Some(access_token);
    Ok(ConfigurationResponse {
        backend_url: config.backend_url,
        default_workspace_id: config.default_workspace_id,
        local_memory_root: config.local_memory_root,
    })
}

#[tauri::command]
async fn login(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    backend_url: String,
    email: String,
    password: String,
    local_memory_root: String,
) -> Result<AuthResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    let client = MemoryClient::for_backend(normalized_backend_url.clone())?;
    let auth = client.login(&email, &password).await?;
    persist_auth_state(app, state, normalized_backend_url, local_memory_root, &auth).await?;
    Ok(auth)
}

#[tauri::command]
async fn register(
    backend_url: String,
    email: String,
    password: String,
    local_memory_root: String,
) -> Result<AuthResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    permissions::validate_local_memory_root(local_memory_root)
        .map_err(DesktopError::configuration)?;
    let client = MemoryClient::for_backend(normalized_backend_url.clone())?;
    let auth = client.register(&email, &password).await?;
    Ok(auth)
}

#[tauri::command]
async fn forgot_password(
    backend_url: String,
    email: String,
) -> Result<PasswordRecoveryResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    let client = MemoryClient::for_backend(normalized_backend_url)?;
    Ok(client.forgot_password(&email).await?)
}

#[tauri::command]
async fn reset_password(
    backend_url: String,
    token: String,
    password: String,
) -> Result<PasswordRecoveryResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    let client = MemoryClient::for_backend(normalized_backend_url)?;
    Ok(client.reset_password(&token, &password).await?)
}

#[tauri::command]
async fn exchange_google_code(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    backend_url: String,
    code: String,
    local_memory_root: String,
) -> Result<AuthResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    permissions::validate_local_memory_root(local_memory_root.clone())
        .map_err(DesktopError::configuration)?;
    let client = MemoryClient::for_backend(normalized_backend_url.clone())?;
    let auth = client.exchange_google_code(&code).await?;
    persist_auth_state(app, state, normalized_backend_url, local_memory_root, &auth).await?;
    Ok(auth)
}

#[tauri::command]
async fn login_with_google(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    backend_url: String,
    local_memory_root: String,
) -> Result<AuthResponse, DesktopError> {
    let normalized_backend_url = normalize_backend_url(&backend_url)?;
    permissions::validate_local_memory_root(local_memory_root.clone())
        .map_err(DesktopError::configuration)?;
    let listener = TcpListener::bind("127.0.0.1:0").map_err(|error| {
        DesktopError::tool(format!("failed to start local Google callback: {error}"))
    })?;
    listener
        .set_nonblocking(false)
        .map_err(|error| DesktopError::tool(format!("failed to configure callback: {error}")))?;
    let port = listener
        .local_addr()
        .map_err(|error| DesktopError::tool(format!("failed to read callback port: {error}")))?
        .port();
    let return_to = format!("http://127.0.0.1:{port}/ari/google/callback");
    let auth_url = format!(
        "{}/api/v1/auth/google/start?client=desktop&return_to={}",
        normalized_backend_url,
        url_encode(&return_to)
    );

    // Google OAuth returns to a short-lived localhost callback. The blocking
    // listener is isolated in a worker thread so the Tauri runtime stays alive.
    tools::browser::open_auth_url(&auth_url).map_err(DesktopError::tool)?;
    let code = tokio::task::spawn_blocking(move || wait_for_google_callback(listener))
        .await
        .map_err(|error| DesktopError::tool(format!("Google callback task failed: {error}")))??;
    tools::browser::close_auth_callback_window(port);
    focus_main_window(&app);

    let client = MemoryClient::for_backend(normalized_backend_url.clone())?;
    let auth = client.exchange_google_code(&code).await?;
    persist_auth_state(app, state, normalized_backend_url, local_memory_root, &auth).await?;
    Ok(auth)
}

#[tauri::command]
async fn load_desktop_config(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<Option<ConfigurationResponse>, DesktopError> {
    let Some(config) = read_desktop_config(&app)? else {
        return Ok(None);
    };

    let Ok(access_token) = storage::get_token("access_token") else {
        *state.config.write().await = None;
        *state.access_token.write().await = None;
        return Ok(None);
    };

    *state.config.write().await = Some(config.clone());
    *state.access_token.write().await = Some(access_token);
    Ok(Some(ConfigurationResponse {
        backend_url: config.backend_url,
        default_workspace_id: config.default_workspace_id,
        local_memory_root: config.local_memory_root,
    }))
}

#[tauri::command]
async fn clear_desktop_config(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
) -> Result<(), DesktopError> {
    let path = desktop_config_path(&app)?;
    match fs::remove_file(path) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            return Err(DesktopError::storage(format!(
                "failed to remove config: {error}"
            )));
        }
    }

    storage::delete_token("access_token").map_err(|error| {
        DesktopError::storage(format!(
            "failed to remove access token from secure storage: {error}"
        ))
    })?;
    // Removing the config also removes the local workspace encryption key so a
    // future login cannot accidentally reuse old encrypted-memory material.
    if let Some(config) = state.config.read().await.clone() {
        delete_workspace_key(&config.default_workspace_id)?;
    }
    *state.config.write().await = None;
    *state.access_token.write().await = None;
    Ok(())
}

#[tauri::command]
async fn ensure_workspace_key(
    state: State<'_, AppState>,
) -> Result<WorkspaceKeyStatus, DesktopError> {
    let config = state
        .config
        .read()
        .await
        .clone()
        .ok_or_else(|| DesktopError::configuration("desktop is not configured"))?;
    ensure_workspace_key_for_workspace(&config.default_workspace_id)
}

#[tauri::command]
async fn clear_workspace_key(state: State<'_, AppState>) -> Result<(), DesktopError> {
    let config = state
        .config
        .read()
        .await
        .clone()
        .ok_or_else(|| DesktopError::configuration("desktop is not configured"))?;
    delete_workspace_key(&config.default_workspace_id)
}

#[tauri::command]
async fn append_journal_entry(
    state: State<'_, AppState>,
    section: String,
    text: String,
    timestamp: Option<String>,
    date: Option<String>,
) -> Result<JournalEntryResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    let day = date.unwrap_or_else(today_utc);
    Ok(client
        .append_journal_entry(&day, &section, &text, timestamp)
        .await?)
}

#[tauri::command]
async fn read_journal_day(
    state: State<'_, AppState>,
    date: String,
) -> Result<JournalDayResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.read_journal_day(&date).await?)
}

#[tauri::command]
async fn read_journal_overview(
    state: State<'_, AppState>,
    date: String,
) -> Result<JournalOverviewResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.read_journal_overview(&date).await?)
}

#[tauri::command]
async fn search_memory(
    state: State<'_, AppState>,
    query: String,
    limit: Option<u32>,
) -> Result<Vec<SearchResult>, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.search_memory(&query, limit).await?)
}

#[tauri::command]
async fn chat_with_ari(
    state: State<'_, AppState>,
    message: String,
    thread_id: Option<String>,
    use_memory: Option<bool>,
    memory_limit: Option<u32>,
) -> Result<ChatResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .chat(
            &message,
            thread_id.as_deref(),
            use_memory.unwrap_or(true),
            memory_limit,
        )
        .await?)
}

#[tauri::command]
async fn voice_with_ari(
    state: State<'_, AppState>,
    audio_base64: String,
    audio_content_type: Option<String>,
    thread_id: Option<String>,
    tts: Option<bool>,
    use_memory: Option<bool>,
    memory_limit: Option<u32>,
) -> Result<VoiceResponse, DesktopError> {
    let audio = BASE64_STANDARD
        .decode(audio_base64.trim())
        .map_err(|error| {
            DesktopError::configuration(format!("invalid voice audio payload: {error}"))
        })?;
    let content_type = audio_content_type
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .unwrap_or("audio/webm");
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .voice(
            audio,
            content_type,
            thread_id.as_deref(),
            tts.unwrap_or(true),
            use_memory.unwrap_or(true),
            memory_limit,
        )
        .await?)
}

#[tauri::command]
async fn speech_with_ari(
    state: State<'_, AppState>,
    text: String,
) -> Result<SpeechResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.speech(&text).await?)
}

#[tauri::command]
async fn native_voice_with_ari(
    state: State<'_, AppState>,
    thread_id: Option<String>,
    tts: Option<bool>,
    use_memory: Option<bool>,
    memory_limit: Option<u32>,
    duration_seconds: Option<u32>,
) -> Result<VoiceResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    let duration = duration_seconds.unwrap_or(6).clamp(2, 15);
    // Native capture shells out to ffmpeg and can block while recording, so it
    // runs outside the async executor before being uploaded to the backend.
    let audio = tokio::task::spawn_blocking(move || record_microphone_wav(duration))
        .await
        .map_err(|error| DesktopError::tool(format!("native microphone task failed: {error}")))??;
    Ok(client
        .voice(
            audio,
            "audio/wav",
            thread_id.as_deref(),
            tts.unwrap_or(true),
            use_memory.unwrap_or(true),
            memory_limit,
        )
        .await?)
}

#[tauri::command]
fn open_microphone_settings() -> Result<(), DesktopError> {
    #[cfg(target_os = "macos")]
    {
        let output = Command::new("open")
            .arg("x-apple.systempreferences:com.apple.preference.security?Privacy_Microphone")
            .output()
            .map_err(|error| {
                DesktopError::tool(format!("failed to open microphone settings: {error}"))
            })?;
        if output.status.success() {
            Ok(())
        } else {
            Err(DesktopError::tool(format!(
                "failed to open microphone settings: {}",
                String::from_utf8_lossy(&output.stderr).trim()
            )))
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        Err(DesktopError::tool(
            "opening microphone settings is currently supported on macOS only",
        ))
    }
}

#[derive(Debug, Serialize)]
struct MicrophoneDiagnostics {
    ffmpeg_available: bool,
    can_record: bool,
    message: String,
}

#[tauri::command]
fn microphone_diagnostics() -> MicrophoneDiagnostics {
    match record_microphone_wav(1) {
        Ok(audio) if !audio.is_empty() => MicrophoneDiagnostics {
            ffmpeg_available: true,
            can_record: true,
            message: "Microphone capture is available.".to_string(),
        },
        Ok(_) => MicrophoneDiagnostics {
            ffmpeg_available: true,
            can_record: false,
            message: "Microphone capture produced no audio.".to_string(),
        },
        Err(error) => {
            let message = error.message;
            MicrophoneDiagnostics {
                ffmpeg_available: !message.contains("ffmpeg is not available"),
                can_record: false,
                message,
            }
        }
    }
}

#[tauri::command]
fn speak_text_native(text: String) -> Result<(), DesktopError> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err(DesktopError::configuration("text cannot be empty"));
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("say")
            .arg(trimmed)
            .spawn()
            .map(|_| ())
            .map_err(|error| DesktopError::tool(format!("failed to start macOS speech: {error}")))
    }

    #[cfg(not(target_os = "macos"))]
    {
        Err(DesktopError::tool(
            "native text-to-speech is currently supported on macOS only",
        ))
    }
}

#[tauri::command]
async fn list_threads(
    state: State<'_, AppState>,
    limit: Option<u32>,
) -> Result<Vec<ThreadSummary>, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.list_threads(limit).await?)
}

#[tauri::command]
async fn create_thread(
    state: State<'_, AppState>,
    title: Option<String>,
) -> Result<Thread, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.create_thread(title.as_deref()).await?)
}

#[tauri::command]
async fn read_thread(
    state: State<'_, AppState>,
    thread_id: String,
) -> Result<Thread, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.read_thread(&thread_id).await?)
}

#[tauri::command]
async fn orchestrate_with_ari(
    state: State<'_, AppState>,
    message: String,
    pending_action: Option<serde_json::Value>,
    use_memory: Option<bool>,
    memory_limit: Option<u32>,
) -> Result<OrchestrateResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .orchestrate(
            &message,
            pending_action,
            use_memory.unwrap_or(true),
            memory_limit,
        )
        .await?)
}

#[tauri::command]
async fn list_recent_messages(
    state: State<'_, AppState>,
    limit: Option<u32>,
) -> Result<Vec<RecentMessage>, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.recent_messages(limit).await?)
}

#[tauri::command]
async fn read_conversation(
    state: State<'_, AppState>,
    date: String,
    line_number: u32,
) -> Result<Conversation, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.read_conversation(&date, line_number).await?)
}

#[tauri::command]
async fn audit_tool_event(
    state: State<'_, AppState>,
    event_type: String,
    tool_name: Option<String>,
    payload: serde_json::Value,
) -> Result<AuditEventResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.audit_event(&event_type, tool_name, payload).await?)
}

#[tauri::command]
async fn list_audit_events(
    state: State<'_, AppState>,
    limit: Option<u32>,
) -> Result<Vec<AuditEventResponse>, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.list_audit_events(limit).await?)
}

#[tauri::command]
async fn create_backend_action(
    state: State<'_, AppState>,
    tool_name: String,
    params: serde_json::Value,
    idempotency_key: Option<String>,
) -> Result<ActionResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .create_action(&tool_name, params, idempotency_key)
        .await?)
}

#[tauri::command]
async fn confirm_backend_action(
    state: State<'_, AppState>,
    action_id: String,
    confirmation_token: String,
) -> Result<ActionResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .confirm_action(&action_id, &confirmation_token)
        .await?)
}

#[tauri::command]
async fn reject_backend_action(
    state: State<'_, AppState>,
    action_id: String,
) -> Result<ActionResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.reject_action(&action_id).await?)
}

#[tauri::command]
async fn complete_backend_action(
    state: State<'_, AppState>,
    action_id: String,
    status: String,
    result: serde_json::Value,
) -> Result<ActionResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client.complete_action(&action_id, &status, result).await?)
}

// Local tool commands are the last permission gate before touching the host OS.
// The backend may propose actions, but execution still depends on desktop policy.
#[tauri::command]
async fn open_browser_url(url: String) -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("browser.open") {
        return Err(DesktopError::tool("missing permission: browser.open"));
    }
    let opened_url = tools::browser::open_browser_url(&url).map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "open_browser_url",
        "status": "done",
        "url": opened_url
    }))
}

#[tauri::command]
async fn call_phone_number(
    phone_number: String,
    display_name: Option<String>,
) -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("phone.call") {
        return Err(DesktopError::tool("missing permission: phone.call"));
    }
    let normalized = tools::phone::call_phone_number(&phone_number).map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "call_phone_number",
        "status": "done",
        "phone_number": normalized,
        "display_name": display_name
    }))
}

#[tauri::command]
async fn list_calendars() -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("calendar.read") {
        return Err(DesktopError::tool("missing permission: calendar.read"));
    }
    let calendars = tools::calendar::list_calendars().map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "list_calendars",
        "status": "done",
        "calendars": calendars
    }))
}

#[tauri::command]
async fn create_calendar_event(
    calendar: String,
    title: String,
    start: String,
    end: String,
) -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("calendar.write") {
        return Err(DesktopError::tool("missing permission: calendar.write"));
    }
    let event = tools::calendar::create_calendar_event(&calendar, &title, &start, &end)
        .map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "create_calendar_event",
        "status": "done",
        "calendar": event.calendar,
        "title": event.title,
        "start": event.start,
        "end": event.end,
        "event_id": event.event_id
    }))
}

#[tauri::command]
async fn list_reminder_lists() -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("reminders.read") {
        return Err(DesktopError::tool("missing permission: reminders.read"));
    }
    let lists = tools::reminders::list_reminder_lists().map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "list_reminder_lists",
        "status": "done",
        "lists": lists
    }))
}

#[tauri::command]
async fn create_reminder(
    list: String,
    title: String,
    due: String,
) -> Result<serde_json::Value, DesktopError> {
    if !permissions::has_permission("reminders.write") {
        return Err(DesktopError::tool("missing permission: reminders.write"));
    }
    let reminder =
        tools::reminders::create_reminder(&list, &title, &due).map_err(DesktopError::tool)?;
    Ok(serde_json::json!({
        "tool": "create_reminder",
        "status": "done",
        "list": reminder.list,
        "title": reminder.title,
        "due": reminder.due,
        "reminder_id": reminder.reminder_id
    }))
}

async fn persist_auth_state(
    app: tauri::AppHandle,
    state: State<'_, AppState>,
    backend_url: String,
    local_memory_root: String,
    auth: &AuthResponse,
) -> Result<(), DesktopError> {
    // Keep the three auth artifacts in sync: config file, keychain token, and
    // process cache. A partial failure returns before the cache is updated.
    let default_workspace_id = auth.default_workspace_id.clone().ok_or_else(|| {
        DesktopError::configuration("login/register response did not include a default workspace")
    })?;
    let config = build_config(backend_url, default_workspace_id, local_memory_root)?;
    save_desktop_config(&app, &config)?;
    storage::store_token("access_token", &auth.access_token).map_err(|error| {
        DesktopError::storage(format!("failed to store access token securely: {error}"))
    })?;
    ensure_workspace_key_for_workspace(&config.default_workspace_id)?;
    *state.config.write().await = Some(config);
    *state.access_token.write().await = Some(auth.access_token.clone());
    Ok(())
}

fn desktop_config_path(app: &tauri::AppHandle) -> Result<PathBuf, DesktopError> {
    let dir = app
        .path()
        .app_config_dir()
        .map_err(|error| DesktopError::storage(format!("failed to resolve config dir: {error}")))?;
    Ok(dir.join(CONFIG_FILE_NAME))
}

fn save_desktop_config(app: &tauri::AppHandle, config: &DesktopConfig) -> Result<(), DesktopError> {
    let path = desktop_config_path(app)?;
    let parent = path
        .parent()
        .ok_or_else(|| DesktopError::storage("failed to resolve config directory"))?;
    fs::create_dir_all(parent)
        .map_err(|error| DesktopError::storage(format!("failed to create config dir: {error}")))?;
    let content = serde_json::to_string_pretty(config)
        .map_err(|error| DesktopError::storage(format!("failed to encode config: {error}")))?;
    fs::write(path, content)
        .map_err(|error| DesktopError::storage(format!("failed to write config: {error}")))
}

fn read_desktop_config(app: &tauri::AppHandle) -> Result<Option<DesktopConfig>, DesktopError> {
    let path = desktop_config_path(app)?;
    if !path.exists() {
        return Ok(None);
    }

    let content = fs::read_to_string(path)
        .map_err(|error| DesktopError::storage(format!("failed to read config: {error}")))?;
    serde_json::from_str(&content)
        .map(Some)
        .map_err(|error| DesktopError::storage(format!("failed to decode config: {error}")))
}

async fn memory_client_from_state(
    state: &State<'_, AppState>,
) -> Result<MemoryClient, DesktopError> {
    // Rehydrate the bearer token lazily after app restart. Commands can stay
    // small because this helper centralizes config/token validation.
    let config = state
        .config
        .read()
        .await
        .clone()
        .ok_or_else(|| DesktopError::configuration("desktop is not configured"))?;
    let access_token = match state.access_token.read().await.clone() {
        Some(token) => token,
        None => {
            let token = storage::get_token("access_token").map_err(|error| match error {
                keyring::Error::NoEntry => {
                    DesktopError::auth("session expired or missing. Please log in again.")
                }
                _ => DesktopError::storage(format!(
                    "failed to read access token from secure storage: {error}"
                )),
            })?;
            *state.access_token.write().await = Some(token.clone());
            token
        }
    };
    MemoryClient::new(
        config.backend_url,
        access_token,
        config.default_workspace_id,
    )
    .map_err(DesktopError::from)
}

fn build_config(
    backend_url: String,
    default_workspace_id: String,
    local_memory_root: String,
) -> Result<DesktopConfig, DesktopError> {
    Ok(DesktopConfig {
        backend_url: normalize_backend_url(&backend_url)?,
        default_workspace_id: validate_workspace_id(default_workspace_id)?,
        local_memory_root: permissions::validate_local_memory_root(local_memory_root)
            .map_err(DesktopError::configuration)?,
    })
}

fn normalize_backend_url(value: &str) -> Result<String, DesktopError> {
    let trimmed = value.trim().trim_end_matches('/');
    let parsed = url::Url::parse(trimmed)
        .map_err(|_| DesktopError::configuration("backend_url must be a valid absolute URL"))?;
    match parsed.scheme() {
        "http" | "https" => Ok(trimmed.to_string()),
        _ => Err(DesktopError::configuration(
            "backend_url must use http or https",
        )),
    }
}

fn validate_workspace_id(value: String) -> Result<String, DesktopError> {
    let trimmed = value.trim();
    if trimmed.is_empty() {
        return Err(DesktopError::configuration(
            "default_workspace_id cannot be empty",
        ));
    }
    Ok(trimmed.to_string())
}

fn wait_for_google_callback(listener: TcpListener) -> Result<String, DesktopError> {
    // Keep the callback listener local and short-lived. Only the OAuth code is
    // extracted; the browser response is just enough to close the login window.
    listener
        .set_nonblocking(true)
        .map_err(|error| DesktopError::tool(format!("failed to configure callback: {error}")))?;
    listener
        .set_ttl(1)
        .map_err(|error| DesktopError::tool(format!("failed to constrain callback: {error}")))?;
    let deadline = Instant::now() + Duration::from_secs(120);
    let mut stream = loop {
        match listener.accept() {
            Ok((stream, _)) => break stream,
            Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                if Instant::now() >= deadline {
                    return Err(DesktopError::tool("Google login timed out"));
                }
                std::thread::sleep(Duration::from_millis(100));
            }
            Err(error) => {
                return Err(DesktopError::tool(format!(
                    "Google login callback was not received: {error}"
                )));
            }
        }
    };
    stream
        .set_nonblocking(false)
        .map_err(|error| DesktopError::tool(format!("failed to read callback stream: {error}")))?;
    let mut buffer = [0_u8; 8192];
    let read = stream
        .read(&mut buffer)
        .map_err(|error| DesktopError::tool(format!("failed to read Google callback: {error}")))?;
    let request = String::from_utf8_lossy(&buffer[..read]);
    let first_line = request.lines().next().unwrap_or_default();
    let path = first_line
        .split_whitespace()
        .nth(1)
        .ok_or_else(|| DesktopError::tool("Google callback request was malformed"))?;
    let callback_url = url::Url::parse(&format!("http://127.0.0.1{path}"))
        .map_err(|_| DesktopError::tool("Google callback URL was malformed"))?;
    let code = callback_url
        .query_pairs()
        .find_map(|(key, value)| (key == "google_auth").then(|| value.into_owned()))
        .ok_or_else(|| DesktopError::tool("Google callback did not include a login code"))?;
    write_callback_response(&mut stream)?;
    Ok(code)
}

fn write_callback_response(stream: &mut TcpStream) -> Result<(), DesktopError> {
    let body = "<!doctype html><html><head><meta charset=\"utf-8\"><title>ARI Login</title></head><body style=\"background:#1A1208;color:#F7F2EC;font-family:Georgia,serif;display:grid;place-items:center;min-height:100vh;margin:0\"><main><h1>ARI is connected</h1><p>You can return to the desktop app.</p></main><script>function done(){try{window.open('','_self');}catch(e){}try{window.close();}catch(e){}setTimeout(()=>{document.body.innerHTML='<main><h1>ARI is connected</h1><p>This login window can be closed.</p></main>';},800)}setTimeout(done,250)</script></body></html>";
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    stream
        .write_all(response.as_bytes())
        .map_err(|error| DesktopError::tool(format!("failed to finish Google callback: {error}")))
}

fn focus_main_window(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.set_focus();
    }
}

fn url_encode(value: &str) -> String {
    value
        .bytes()
        .flat_map(|byte| match byte {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                vec![byte as char]
            }
            _ => format!("%{byte:02X}").chars().collect(),
        })
        .collect()
}

fn workspace_key_storage_name(workspace_id: &str) -> String {
    format!("workspace_key:{workspace_id}")
}

fn workspace_key_id(workspace_id: &str) -> String {
    format!("workspace-key-{workspace_id}-v1")
}

fn ensure_workspace_key_for_workspace(
    workspace_id: &str,
) -> Result<WorkspaceKeyStatus, DesktopError> {
    // Workspace keys are generated once per workspace and kept out of the JSON
    // config file. The backend only sees wrapped/encrypted forms of this key.
    let storage_name = workspace_key_storage_name(workspace_id);
    match storage::get_token(&storage_name) {
        Ok(_) => Ok(WorkspaceKeyStatus {
            workspace_id: workspace_id.to_string(),
            key_id: workspace_key_id(workspace_id),
            created: false,
        }),
        Err(keyring::Error::NoEntry) => {
            let key = WorkspaceKey::generate();
            storage::store_token(&storage_name, &key.to_base64()).map_err(|error| {
                DesktopError::storage(format!("failed to store workspace key securely: {error}"))
            })?;
            Ok(WorkspaceKeyStatus {
                workspace_id: workspace_id.to_string(),
                key_id: workspace_key_id(workspace_id),
                created: true,
            })
        }
        Err(error) => Err(DesktopError::storage(format!(
            "failed to read workspace key from secure storage: {error}"
        ))),
    }
}

fn delete_workspace_key(workspace_id: &str) -> Result<(), DesktopError> {
    storage::delete_token(&workspace_key_storage_name(workspace_id)).map_err(|error| {
        DesktopError::storage(format!(
            "failed to remove workspace key from secure storage: {error}"
        ))
    })
}

fn today_utc() -> String {
    Utc::now().date_naive().format("%Y-%m-%d").to_string()
}

fn record_microphone_wav(duration_seconds: u32) -> Result<Vec<u8>, DesktopError> {
    // ffmpeg records a temporary mono 16 kHz WAV because the backend voice
    // endpoint accepts simple audio bytes and does not need desktop state.
    let output_path = std::env::temp_dir().join(format!(
        "ari-voice-{}-{}.wav",
        std::process::id(),
        Utc::now().timestamp_millis()
    ));
    let ffmpeg = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "ffmpeg",
    ]
    .into_iter()
    .find(|candidate| {
        if candidate.contains('/') {
            PathBuf::from(candidate).exists()
        } else {
            true
        }
    })
    .ok_or_else(|| DesktopError::tool("ffmpeg is not available for native microphone capture"))?;

    let duration_arg = duration_seconds.to_string();
    let output = Command::new(ffmpeg)
        .args([
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            ":0",
            "-t",
            &duration_arg,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-y",
        ])
        .arg(&output_path)
        .output()
        .map_err(|error| {
            DesktopError::tool(format!(
                "failed to start native microphone capture: {error}"
            ))
        })?;

    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();
        let _ = fs::remove_file(&output_path);
        return Err(DesktopError::tool(if stderr.is_empty() {
            "native microphone capture failed".to_string()
        } else {
            format!("native microphone capture failed: {stderr}")
        }));
    }

    let audio = fs::read(&output_path).map_err(|error| {
        DesktopError::tool(format!("failed to read native microphone audio: {error}"))
    })?;
    let _ = fs::remove_file(&output_path);
    if audio.is_empty() {
        return Err(DesktopError::tool(
            "native microphone capture produced no audio",
        ));
    }
    Ok(audio)
}

pub fn run() {
    // Every function in this handler is callable from `desktop/ui/index.html`.
    // Add new desktop commands here only after checking their permission model.
    tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            default_backend_url,
            configure_desktop,
            login,
            register,
            forgot_password,
            reset_password,
            exchange_google_code,
            login_with_google,
            load_desktop_config,
            clear_desktop_config,
            ensure_workspace_key,
            clear_workspace_key,
            append_journal_entry,
            read_journal_day,
            read_journal_overview,
            search_memory,
            chat_with_ari,
            voice_with_ari,
            speech_with_ari,
            native_voice_with_ari,
            open_microphone_settings,
            microphone_diagnostics,
            speak_text_native,
            list_threads,
            create_thread,
            read_thread,
            orchestrate_with_ari,
            list_recent_messages,
            read_conversation,
            audit_tool_event,
            list_audit_events,
            create_backend_action,
            confirm_backend_action,
            reject_backend_action,
            complete_backend_action,
            open_browser_url,
            call_phone_number,
            list_calendars,
            create_calendar_event,
            list_reminder_lists,
            create_reminder
        ])
        .run(tauri::generate_context!())
        .expect("error while running AI Assistant desktop app");
}

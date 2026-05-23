pub mod agent;
pub mod memory;
pub mod permissions;
pub mod storage;
pub mod tools;

use chrono::Utc;
use memory::client::{
    ActionResponse, AuditEventResponse, AuthResponse, ChatResponse, Conversation,
    JournalDayResponse, JournalEntryResponse, JournalOverviewResponse, MemoryClient,
    MemoryClientError, OrchestrateResponse, PasswordRecoveryResponse, RecentMessage, SearchResult,
};
use memory::crypto::WorkspaceKey;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tauri::{Manager, State};
use tokio::sync::RwLock;

const CONFIG_FILE_NAME: &str = "desktop-config.json";
const PRODUCTION_BACKEND_URL: &str = "https://ari.flusscreative.com";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DesktopConfig {
    pub backend_url: String,
    pub default_workspace_id: String,
    pub local_memory_root: PathBuf,
}

#[derive(Debug, Default)]
pub struct AppState {
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

    tools::browser::open_browser_url(&auth_url).map_err(DesktopError::tool)?;
    let code = tokio::task::spawn_blocking(move || wait_for_google_callback(listener))
        .await
        .map_err(|error| DesktopError::tool(format!("Google callback task failed: {error}")))??;

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
    use_memory: Option<bool>,
    memory_limit: Option<u32>,
) -> Result<ChatResponse, DesktopError> {
    let client = memory_client_from_state(&state).await?;
    Ok(client
        .chat(&message, use_memory.unwrap_or(true), memory_limit)
        .await?)
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
    let body = "<!doctype html><html><head><meta charset=\"utf-8\"><title>ARI Login</title></head><body style=\"background:#1A1208;color:#F7F2EC;font-family:Georgia,serif;display:grid;place-items:center;min-height:100vh;margin:0\"><main><h1>ARI is connected</h1><p>You can return to the desktop app.</p></main><script>setTimeout(()=>window.close(),900)</script></body></html>";
    let response = format!(
        "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
        body.len(),
        body
    );
    stream
        .write_all(response.as_bytes())
        .map_err(|error| DesktopError::tool(format!("failed to finish Google callback: {error}")))
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

pub fn run() {
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

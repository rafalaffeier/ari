use serde::{Deserialize, Serialize};
use thiserror::Error;
use url::Url;

use super::crypto::{EncryptedMarkdown, EncryptionEnvelope};

#[derive(Debug, Clone)]
pub struct MemoryClient {
    backend_url: String,
    access_token: Option<String>,
    workspace_id: String,
    http: reqwest::Client,
}

#[derive(Debug, Error)]
pub enum MemoryClientError {
    #[error("configuration error: {0}")]
    Configuration(String),
    #[error("backend request failed: {0}")]
    Request(#[from] reqwest::Error),
    #[error("backend returned {status}: {body}")]
    Api {
        status: reqwest::StatusCode,
        body: String,
    },
    #[error("backend response was missing {0}")]
    MissingHeader(&'static str),
}

impl MemoryClientError {
    pub fn kind(&self) -> &'static str {
        match self {
            Self::Configuration(_) => "configuration",
            Self::Request(_) => "network",
            Self::Api { status, .. } if *status == reqwest::StatusCode::UNAUTHORIZED => "auth",
            Self::Api { status, .. } if *status == reqwest::StatusCode::FORBIDDEN => "auth",
            Self::Api { .. } => "api",
            Self::MissingHeader(_) => "api",
        }
    }
}

#[derive(Debug, Serialize)]
struct RegisterRequest<'a> {
    email: &'a str,
    password: &'a str,
}

#[derive(Debug, Serialize)]
struct ForgotPasswordRequest<'a> {
    email: &'a str,
}

#[derive(Debug, Serialize)]
struct ResetPasswordRequest<'a> {
    token: &'a str,
    password: &'a str,
}

#[derive(Debug, Serialize)]
struct GoogleExchangeRequest<'a> {
    code: &'a str,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct AuthResponse {
    pub access_token: String,
    pub token_type: String,
    pub user_id: String,
    pub default_workspace_id: Option<String>,
    pub email: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct PasswordRecoveryResponse {
    pub detail: String,
    pub reset_url: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct JournalEntryRequest {
    pub section: String,
    pub text: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub timestamp: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JournalEntryResponse {
    pub workspace_id: String,
    pub date: String,
    pub path: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JournalDayResponse {
    pub workspace_id: String,
    pub date: String,
    pub content: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct JournalOverviewResponse {
    pub workspace_id: String,
    pub date: String,
    pub sections: serde_json::Value,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct SearchResult {
    pub date: String,
    pub path: String,
    pub line_number: u32,
    pub line: String,
}

#[derive(Debug, Serialize)]
pub struct ChatRequest<'a> {
    pub message: &'a str,
    pub use_memory: bool,
    pub memory_limit: u32,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ChatResponse {
    pub reply: String,
    pub model: String,
    pub memory_results: Vec<SearchResult>,
    pub stored: bool,
}

#[derive(Debug, Serialize)]
pub struct OrchestrateRequest<'a> {
    pub message: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pending_action: Option<serde_json::Value>,
    pub use_memory: bool,
    pub memory_limit: u32,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct OrchestrateResponse {
    pub mode: String,
    pub reply: String,
    pub tool_name: Option<String>,
    pub params: serde_json::Value,
    pub missing: Vec<String>,
    pub requires_confirmation: bool,
    pub confidence: f64,
    pub language: String,
    pub model: String,
    pub memory_results: Vec<SearchResult>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct RecentMessage {
    pub date: String,
    pub line_number: u32,
    pub title: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ConversationMessage {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct Conversation {
    pub date: String,
    pub line_number: u32,
    pub title: String,
    pub messages: Vec<ConversationMessage>,
}

#[derive(Debug, Serialize)]
pub struct AuditEventRequest {
    pub event_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tool_name: Option<String>,
    pub payload: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device_id: Option<String>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct AuditEventResponse {
    pub id: String,
    pub workspace_id: Option<String>,
    pub user_id: Option<String>,
    pub device_id: Option<String>,
    pub event_type: String,
    pub payload: serde_json::Value,
    pub hash_previous: Option<String>,
    pub hash_current: String,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
pub struct ActionCreateRequest {
    pub tool_name: String,
    pub params: serde_json::Value,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub device_id: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub idempotency_key: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ActionConfirmRequest {
    pub confirmation_token: String,
}

#[derive(Debug, Serialize)]
pub struct ActionResultRequest {
    pub status: String,
    pub result: serde_json::Value,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct ActionResponse {
    pub id: String,
    pub workspace_id: String,
    pub user_id: String,
    pub device_id: Option<String>,
    pub tool_name: String,
    pub tool_version: String,
    pub params: serde_json::Value,
    pub status: String,
    pub risk_level: String,
    pub requires_confirmation: bool,
    pub confirmation_token: Option<String>,
    pub confirmed_at: Option<String>,
    pub result: Option<serde_json::Value>,
    pub created_at: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct FileVersionResponse {
    pub id: String,
    pub workspace_id: String,
    pub path: String,
    pub version: u32,
    pub checksum_sha256: String,
    pub size_bytes: u64,
    pub modified_at: String,
    pub storage_key: Option<String>,
    pub encryption_metadata: Option<EncryptionEnvelope>,
    pub updated_by_user_id: String,
    pub created_at: String,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct FileContentUploadResponse {
    #[serde(flatten)]
    pub file: FileVersionResponse,
    pub download_url: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DownloadedEncryptedMarkdown {
    pub ciphertext: Vec<u8>,
    pub path: String,
    pub version: u32,
    pub checksum_sha256: String,
    pub size_bytes: u64,
    pub envelope: EncryptionEnvelope,
}

#[derive(Debug, Serialize)]
struct WorkspaceKeyWrapRequest<'a> {
    device_id: &'a str,
    key_id: &'a str,
    wrapping_algorithm: &'a str,
    wrapped_key: &'a str,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct WorkspaceKeyWrapResponse {
    pub id: String,
    pub workspace_id: String,
    pub device_id: String,
    pub key_id: String,
    pub wrapping_algorithm: String,
    pub wrapped_key: String,
    pub created_by_user_id: String,
    pub created_at: String,
}

#[derive(Debug, Serialize)]
struct WorkspaceRecoveryWrapRequest<'a> {
    key_id: &'a str,
    wrapping_algorithm: &'a str,
    wrapped_key: &'a str,
    #[serde(skip_serializing_if = "Option::is_none")]
    recovery_hint: Option<&'a str>,
}

#[derive(Debug, Deserialize, Serialize)]
pub struct WorkspaceRecoveryWrapResponse {
    pub id: String,
    pub workspace_id: String,
    pub key_id: String,
    pub wrapping_algorithm: String,
    pub wrapped_key: String,
    pub recovery_hint: Option<String>,
    pub created_by_user_id: String,
    pub created_at: String,
}

impl MemoryClient {
    pub fn for_backend(backend_url: String) -> Result<Self, MemoryClientError> {
        Self::build(backend_url, None, String::new())
    }

    pub fn new(
        backend_url: String,
        access_token: String,
        workspace_id: String,
    ) -> Result<Self, MemoryClientError> {
        if access_token.trim().is_empty() {
            return Err(MemoryClientError::Configuration(
                "access token cannot be empty".to_string(),
            ));
        }
        if workspace_id.trim().is_empty() {
            return Err(MemoryClientError::Configuration(
                "workspace id cannot be empty".to_string(),
            ));
        }
        Self::build(backend_url, Some(access_token), workspace_id)
    }

    pub async fn register(
        &self,
        email: &str,
        password: &str,
    ) -> Result<AuthResponse, MemoryClientError> {
        let url = format!("{}/api/v1/auth/register", self.backend_url);
        self.send_json(
            self.http
                .post(url)
                .json(&RegisterRequest { email, password }),
        )
        .await
    }

    pub async fn login(
        &self,
        email: &str,
        password: &str,
    ) -> Result<AuthResponse, MemoryClientError> {
        let url = format!("{}/api/v1/auth/login", self.backend_url);
        self.send_json(
            self.http
                .post(url)
                .form(&[("username", email), ("password", password)]),
        )
        .await
    }

    pub async fn forgot_password(
        &self,
        email: &str,
    ) -> Result<PasswordRecoveryResponse, MemoryClientError> {
        let url = format!("{}/api/v1/auth/forgot-password", self.backend_url);
        self.send_json(self.http.post(url).json(&ForgotPasswordRequest { email }))
            .await
    }

    pub async fn reset_password(
        &self,
        token: &str,
        password: &str,
    ) -> Result<PasswordRecoveryResponse, MemoryClientError> {
        let url = format!("{}/api/v1/auth/reset-password", self.backend_url);
        self.send_json(
            self.http
                .post(url)
                .json(&ResetPasswordRequest { token, password }),
        )
        .await
    }

    pub async fn exchange_google_code(
        &self,
        code: &str,
    ) -> Result<AuthResponse, MemoryClientError> {
        let url = format!("{}/api/v1/auth/google/exchange", self.backend_url);
        self.send_json(self.http.post(url).json(&GoogleExchangeRequest { code }))
            .await
    }

    pub async fn append_journal_entry(
        &self,
        date: &str,
        section: &str,
        text: &str,
        timestamp: Option<String>,
    ) -> Result<JournalEntryResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/memory/{}/journal/{}/entries",
            self.backend_url, self.workspace_id, date
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&JournalEntryRequest {
                    section: section.to_string(),
                    text: text.to_string(),
                    timestamp,
                }),
        )
        .await
    }

    pub async fn read_journal_day(
        &self,
        date: &str,
    ) -> Result<JournalDayResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/memory/{}/journal/{}",
            self.backend_url, self.workspace_id, date
        );
        self.send_json(self.authorized(self.http.get(url))?).await
    }

    pub async fn read_journal_overview(
        &self,
        date: &str,
    ) -> Result<JournalOverviewResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/memory/{}/journal/{}/overview",
            self.backend_url, self.workspace_id, date
        );
        self.send_json(self.authorized(self.http.get(url))?).await
    }

    pub async fn search_memory(
        &self,
        query: &str,
        limit: Option<u32>,
    ) -> Result<Vec<SearchResult>, MemoryClientError> {
        let url = format!(
            "{}/api/v1/memory/{}/search",
            self.backend_url, self.workspace_id
        );
        let limit_value = limit.unwrap_or(20).to_string();
        self.send_json(
            self.authorized(self.http.get(url))?
                .query(&[("q", query), ("limit", limit_value.as_str())]),
        )
        .await
    }

    pub async fn chat(
        &self,
        message: &str,
        use_memory: bool,
        memory_limit: Option<u32>,
    ) -> Result<ChatResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/messages/{}/chat",
            self.backend_url, self.workspace_id
        );
        self.send_json(self.authorized(self.http.post(url))?.json(&ChatRequest {
            message,
            use_memory,
            memory_limit: memory_limit.unwrap_or(8),
        }))
        .await
    }

    pub async fn orchestrate(
        &self,
        message: &str,
        pending_action: Option<serde_json::Value>,
        use_memory: bool,
        memory_limit: Option<u32>,
    ) -> Result<OrchestrateResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/messages/{}/orchestrate",
            self.backend_url, self.workspace_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&OrchestrateRequest {
                    message,
                    pending_action,
                    use_memory,
                    memory_limit: memory_limit.unwrap_or(8),
                }),
        )
        .await
    }

    pub async fn recent_messages(
        &self,
        limit: Option<u32>,
    ) -> Result<Vec<RecentMessage>, MemoryClientError> {
        let url = format!(
            "{}/api/v1/messages/{}/recent",
            self.backend_url, self.workspace_id
        );
        let limit_value = limit.unwrap_or(20).to_string();
        self.send_json(
            self.authorized(self.http.get(url))?
                .query(&[("limit", limit_value.as_str())]),
        )
        .await
    }

    pub async fn read_conversation(
        &self,
        date: &str,
        line_number: u32,
    ) -> Result<Conversation, MemoryClientError> {
        let url = format!(
            "{}/api/v1/messages/{}/conversation/{}/{}",
            self.backend_url, self.workspace_id, date, line_number
        );
        self.send_json(self.authorized(self.http.get(url))?).await
    }

    pub async fn audit_event(
        &self,
        event_type: &str,
        tool_name: Option<String>,
        payload: serde_json::Value,
    ) -> Result<AuditEventResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/audit/{}/events",
            self.backend_url, self.workspace_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&AuditEventRequest {
                    event_type: event_type.to_string(),
                    tool_name,
                    payload,
                    device_id: None,
                }),
        )
        .await
    }

    pub async fn list_audit_events(
        &self,
        limit: Option<u32>,
    ) -> Result<Vec<AuditEventResponse>, MemoryClientError> {
        let url = format!(
            "{}/api/v1/audit/{}/events",
            self.backend_url, self.workspace_id
        );
        let limit_value = limit.unwrap_or(50).to_string();
        self.send_json(
            self.authorized(self.http.get(url))?
                .query(&[("limit", limit_value.as_str())]),
        )
        .await
    }

    pub async fn create_action(
        &self,
        tool_name: &str,
        params: serde_json::Value,
        idempotency_key: Option<String>,
    ) -> Result<ActionResponse, MemoryClientError> {
        let url = format!("{}/api/v1/actions/{}", self.backend_url, self.workspace_id);
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&ActionCreateRequest {
                    tool_name: tool_name.to_string(),
                    params,
                    device_id: None,
                    idempotency_key,
                }),
        )
        .await
    }

    pub async fn confirm_action(
        &self,
        action_id: &str,
        confirmation_token: &str,
    ) -> Result<ActionResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/actions/{}/{}/confirm",
            self.backend_url, self.workspace_id, action_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&ActionConfirmRequest {
                    confirmation_token: confirmation_token.to_string(),
                }),
        )
        .await
    }

    pub async fn reject_action(
        &self,
        action_id: &str,
    ) -> Result<ActionResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/actions/{}/{}/reject",
            self.backend_url, self.workspace_id, action_id
        );
        self.send_json(self.authorized(self.http.post(url))?).await
    }

    pub async fn complete_action(
        &self,
        action_id: &str,
        status: &str,
        result: serde_json::Value,
    ) -> Result<ActionResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/actions/{}/{}/result",
            self.backend_url, self.workspace_id, action_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&ActionResultRequest {
                    status: status.to_string(),
                    result,
                }),
        )
        .await
    }

    pub async fn upload_encrypted_markdown(
        &self,
        path: &str,
        encrypted: &EncryptedMarkdown,
        base_version: Option<u32>,
    ) -> Result<FileContentUploadResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/files/content",
            self.backend_url, self.workspace_id
        );
        let mut request = self
            .authorized(self.http.put(url))?
            .query(&[("path", path)])
            .header("Content-Type", "application/octet-stream")
            .header("X-Encryption-Algorithm", &encrypted.envelope.algorithm)
            .header("X-Encryption-Key-Id", &encrypted.envelope.key_id)
            .header("X-Encryption-Nonce", &encrypted.envelope.nonce)
            .header(
                "X-Encryption-Envelope-Version",
                encrypted.envelope.envelope_version.to_string(),
            )
            .body(encrypted.ciphertext.clone());
        let base_version_value;
        if let Some(base_version) = base_version {
            base_version_value = base_version.to_string();
            request = request.query(&[("base_version", base_version_value.as_str())]);
        }
        self.send_json(request).await
    }

    pub async fn download_encrypted_markdown(
        &self,
        path: &str,
    ) -> Result<DownloadedEncryptedMarkdown, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/files/content",
            self.backend_url, self.workspace_id
        );
        let response = self
            .authorized(self.http.get(url))?
            .query(&[("path", path)])
            .send()
            .await?;
        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(MemoryClientError::Api { status, body });
        }
        let headers = response.headers().clone();
        let version = header_value(&headers, "x-file-version")?
            .parse()
            .map_err(|_| MemoryClientError::MissingHeader("x-file-version"))?;
        let size_bytes = header_value(&headers, "x-size-bytes")?
            .parse()
            .map_err(|_| MemoryClientError::MissingHeader("x-size-bytes"))?;
        let envelope_version = header_value(&headers, "x-encryption-envelope-version")?
            .parse()
            .map_err(|_| MemoryClientError::MissingHeader("x-encryption-envelope-version"))?;
        let checksum_sha256 = header_value(&headers, "x-checksum-sha256")?;
        let algorithm = header_value(&headers, "x-encryption-algorithm")?;
        let key_id = header_value(&headers, "x-encryption-key-id")?;
        let nonce = header_value(&headers, "x-encryption-nonce")?;
        let ciphertext = response.bytes().await?.to_vec();

        Ok(DownloadedEncryptedMarkdown {
            ciphertext,
            path: path.to_string(),
            version,
            checksum_sha256,
            size_bytes,
            envelope: EncryptionEnvelope {
                envelope_version,
                algorithm,
                key_id,
                nonce,
            },
        })
    }

    pub async fn upsert_workspace_key_wrap(
        &self,
        device_id: &str,
        key_id: &str,
        wrapping_algorithm: &str,
        wrapped_key: &str,
    ) -> Result<WorkspaceKeyWrapResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/keys/wraps",
            self.backend_url, self.workspace_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&WorkspaceKeyWrapRequest {
                    device_id,
                    key_id,
                    wrapping_algorithm,
                    wrapped_key,
                }),
        )
        .await
    }

    pub async fn list_workspace_key_wraps(
        &self,
        device_id: &str,
    ) -> Result<Vec<WorkspaceKeyWrapResponse>, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/keys/wraps",
            self.backend_url, self.workspace_id
        );
        self.send_json(
            self.authorized(self.http.get(url))?
                .query(&[("device_id", device_id)]),
        )
        .await
    }

    pub async fn upsert_workspace_recovery_wrap(
        &self,
        key_id: &str,
        wrapping_algorithm: &str,
        wrapped_key: &str,
        recovery_hint: Option<&str>,
    ) -> Result<WorkspaceRecoveryWrapResponse, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/keys/recovery",
            self.backend_url, self.workspace_id
        );
        self.send_json(
            self.authorized(self.http.post(url))?
                .json(&WorkspaceRecoveryWrapRequest {
                    key_id,
                    wrapping_algorithm,
                    wrapped_key,
                    recovery_hint,
                }),
        )
        .await
    }

    pub async fn list_workspace_recovery_wraps(
        &self,
    ) -> Result<Vec<WorkspaceRecoveryWrapResponse>, MemoryClientError> {
        let url = format!(
            "{}/api/v1/sync/{}/keys/recovery",
            self.backend_url, self.workspace_id
        );
        self.send_json(self.authorized(self.http.get(url))?).await
    }

    fn build(
        backend_url: String,
        access_token: Option<String>,
        workspace_id: String,
    ) -> Result<Self, MemoryClientError> {
        let backend_url = backend_url.trim().trim_end_matches('/').to_string();
        let parsed = Url::parse(&backend_url).map_err(|_| {
            MemoryClientError::Configuration("backend_url must be an absolute URL".to_string())
        })?;
        match parsed.scheme() {
            "http" | "https" => Ok(Self {
                backend_url,
                access_token,
                workspace_id,
                http: reqwest::Client::new(),
            }),
            _ => Err(MemoryClientError::Configuration(
                "backend_url must use http or https".to_string(),
            )),
        }
    }

    fn authorized(
        &self,
        request: reqwest::RequestBuilder,
    ) -> Result<reqwest::RequestBuilder, MemoryClientError> {
        let token = self.access_token.as_deref().ok_or_else(|| {
            MemoryClientError::Configuration("access token is required".to_string())
        })?;
        Ok(request.bearer_auth(token))
    }

    async fn send_json<T: for<'de> Deserialize<'de>>(
        &self,
        request: reqwest::RequestBuilder,
    ) -> Result<T, MemoryClientError> {
        let response = request.send().await?;
        let status = response.status();
        if !status.is_success() {
            let body = response.text().await.unwrap_or_default();
            return Err(MemoryClientError::Api { status, body });
        }
        Ok(response.json().await?)
    }
}

fn header_value(
    headers: &reqwest::header::HeaderMap,
    name: &'static str,
) -> Result<String, MemoryClientError> {
    headers
        .get(name)
        .and_then(|value| value.to_str().ok())
        .map(ToString::to_string)
        .ok_or(MemoryClientError::MissingHeader(name))
}

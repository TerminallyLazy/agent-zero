use serde::{Deserialize, Serialize};

use a0_core::{BuildInfo, ConversationLog, PluginSummary};
use a0_observability::HealthSnapshot;

#[derive(Debug, Serialize)]
pub struct SuccessEnvelope<T> {
    pub ok: bool,
    pub request_id: String,
    #[serde(flatten)]
    pub data: T,
}

#[derive(Debug, Serialize)]
pub struct VersionResponse {
    pub version: String,
    pub commit: Option<String>,
}

impl From<BuildInfo> for VersionResponse {
    fn from(value: BuildInfo) -> Self {
        Self { version: value.version, commit: value.commit }
    }
}

#[derive(Debug, Serialize)]
pub struct ReadyResponse {
    pub status: &'static str,
    pub ready: bool,
    pub components: Vec<a0_observability::ComponentSnapshot>,
}

impl From<HealthSnapshot> for ReadyResponse {
    fn from(value: HealthSnapshot) -> Self {
        Self { status: value.status, ready: value.ready, components: value.components }
    }
}

#[derive(Debug, Serialize)]
pub struct PluginListResponse {
    pub plugins: Vec<PluginSummary>,
}

#[derive(Debug, Serialize)]
pub struct SettingsResponse {
    pub server_host: String,
    pub server_port: u16,
    pub bridge_mode: String,
}

#[derive(Debug, Deserialize)]
pub struct AttachmentPayload {
    pub filename: String,
    pub base64: String,
}

#[derive(Debug, Deserialize)]
pub struct ApiMessageRequest {
    pub context_id: Option<String>,
    pub message: String,
    pub attachments: Option<Vec<AttachmentPayload>>,
    pub lifetime_hours: Option<u64>,
    pub project_name: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct ApiMessageResponse {
    pub context_id: String,
    pub response: String,
}

#[derive(Debug, Deserialize, Default)]
pub struct ApiLogQuery {
    pub context_id: Option<String>,
    pub length: Option<usize>,
}

#[derive(Debug, Serialize)]
pub struct ApiLogResponse {
    pub context_id: String,
    pub log: ConversationLog,
}

#[derive(Debug, Deserialize, Default)]
pub struct UiMessageRequest {
    pub text: Option<String>,
    pub context: Option<String>,
    #[serde(rename = "message_id")]
    pub _message_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct UiMessageResponse {
    pub message: String,
    pub context: String,
}

#[derive(Debug, Serialize)]
pub struct CsrfTokenResponse {
    pub ok: bool,
    pub token: String,
    pub runtime_id: String,
}

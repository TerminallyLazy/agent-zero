use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BuildInfo {
    pub version: String,
    pub commit: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ContextSummary {
    pub id: String,
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct PluginSummary {
    pub name: String,
    pub enabled: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct JobSummary {
    pub id: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ToolSummary {
    pub name: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SendMessageRequest {
    pub context_id: Option<String>,
    pub message: String,
    pub attachment_filenames: Vec<String>,
    pub lifetime_hours: u64,
    pub project_name: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SendMessageResponse {
    pub context_id: String,
    pub response: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ConversationLogItem {
    pub index: usize,
    pub role: String,
    pub content: String,
    pub attachments: Vec<String>,
    pub created_at: DateTime<Utc>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ConversationLog {
    pub context_id: String,
    pub guid: String,
    pub total_items: usize,
    pub returned_items: usize,
    pub start_position: usize,
    pub progress: Option<String>,
    pub progress_active: bool,
    pub items: Vec<ConversationLogItem>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CreateContextRequest {
    pub current_context: Option<String>,
    pub new_context: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct CreateContextResponse {
    pub ok: bool,
    pub ctxid: String,
    pub message: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct StateSnapshotRequest {
    pub context: Option<String>,
    #[serde(default)]
    pub log_from: usize,
    #[serde(default)]
    pub notifications_from: usize,
    #[serde(default)]
    pub timezone: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct UiContextEntry {
    pub id: String,
    pub name: Option<String>,
    pub created_at: DateTime<Utc>,
    pub no: u64,
    pub log_guid: String,
    pub log_version: usize,
    pub log_length: usize,
    pub paused: bool,
    pub last_message: DateTime<Utc>,
    #[serde(rename = "type")]
    pub kind: String,
    pub running: bool,
    pub project: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StateSnapshot {
    pub deselect_chat: bool,
    pub context: String,
    pub contexts: Vec<UiContextEntry>,
    pub tasks: Vec<Value>,
    pub logs: Vec<Value>,
    pub log_guid: String,
    pub log_version: usize,
    pub log_progress: Value,
    pub log_progress_active: bool,
    pub paused: bool,
    pub notifications: Vec<Value>,
    pub notifications_guid: String,
    pub notifications_version: usize,
}

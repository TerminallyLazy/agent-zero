use std::{
    collections::HashMap,
    sync::{Arc, RwLock},
};

use async_trait::async_trait;
use chrono::{DateTime, Duration, Utc};
use uuid::Uuid;

use serde_json::json;

use crate::{
    AppError, ConversationLog, ConversationLogItem, ConversationService, CreateContextRequest,
    CreateContextResponse, SendMessageRequest, SendMessageResponse, StateSnapshot,
    StateSnapshotRequest, UiContextEntry,
};

#[derive(Debug, Default, Clone)]
pub struct InMemoryConversationService {
    inner: Arc<RwLock<ConversationStore>>,
}

#[derive(Debug, Default)]
struct ConversationStore {
    next_no: u64,
    conversations: HashMap<String, ConversationState>,
}

#[derive(Debug, Clone)]
struct ConversationState {
    id: String,
    no: u64,
    name: Option<String>,
    project_name: Option<String>,
    created_at: DateTime<Utc>,
    last_message: DateTime<Utc>,
    expires_at: DateTime<Utc>,
    paused: bool,
    running: bool,
    items: Vec<ConversationLogItem>,
}

#[async_trait]
impl ConversationService for InMemoryConversationService {
    async fn send_external_message(
        &self,
        request: SendMessageRequest,
    ) -> Result<SendMessageResponse, AppError> {
        self.prune_expired();

        if request.message.trim().is_empty() && request.attachment_filenames.is_empty() {
            return Err(AppError::InvalidRequest(
                "message or attachments are required".to_string(),
            ));
        }

        let now = Utc::now();
        let mut store = self.inner.write().expect("conversation lock poisoned");

        let state = match request.context_id.clone() {
            Some(context_id) => {
                let state = store
                    .conversations
                    .get_mut(&context_id)
                    .ok_or_else(|| AppError::NotFound("Context not found".to_string()))?;

                if let Some(project_name) = &request.project_name {
                    if let Some(existing) = &state.project_name {
                        if existing != project_name {
                            return Err(AppError::InvalidRequest(
                                "Project can only be set on first message".to_string(),
                            ));
                        }
                    }
                }

                state
            }
            None => {
                let context_id = Uuid::new_v4().to_string();
                store.next_no += 1;
                let next_no = store.next_no;
                store.conversations.entry(context_id.clone()).or_insert(ConversationState {
                    id: context_id,
                    no: next_no,
                    name: None,
                    project_name: request.project_name.clone(),
                    created_at: now,
                    last_message: now,
                    expires_at: now + Duration::hours(request.lifetime_hours as i64),
                    paused: false,
                    running: false,
                    items: Vec::new(),
                })
            }
        };

        state.expires_at = now + Duration::hours(request.lifetime_hours as i64);
        state.last_message = now;

        let user_index = state.items.len();
        state.items.push(ConversationLogItem {
            index: user_index,
            role: "user".to_string(),
            content: request.message.clone(),
            attachments: request.attachment_filenames.clone(),
            created_at: now,
        });

        let mut response = if request.message.trim().is_empty() {
            "Rust skeleton received attachments".to_string()
        } else {
            format!("Rust skeleton received: {}", request.message)
        };
        if !request.attachment_filenames.is_empty() {
            response.push_str(&format!(
                " ({} attachment{})",
                request.attachment_filenames.len(),
                if request.attachment_filenames.len() == 1 { "" } else { "s" }
            ));
        }

        let assistant_index = state.items.len();
        state.items.push(ConversationLogItem {
            index: assistant_index,
            role: "assistant".to_string(),
            content: response.clone(),
            attachments: Vec::new(),
            created_at: now,
        });

        Ok(SendMessageResponse { context_id: state.id.clone(), response })
    }

    async fn get_log(&self, context_id: &str, length: usize) -> Result<ConversationLog, AppError> {
        self.prune_expired();

        let store = self.inner.read().expect("conversation lock poisoned");
        let state = store
            .conversations
            .get(context_id)
            .ok_or_else(|| AppError::NotFound("Context not found".to_string()))?;

        let total_items = state.items.len();
        let start_position = total_items.saturating_sub(length);
        let items = state.items[start_position..].to_vec();

        Ok(ConversationLog {
            context_id: context_id.to_string(),
            guid: context_id.to_string(),
            total_items,
            returned_items: items.len(),
            start_position,
            progress: None,
            progress_active: false,
            items,
        })
    }

    async fn create_context(
        &self,
        request: CreateContextRequest,
    ) -> Result<CreateContextResponse, AppError> {
        self.prune_expired();

        let now = Utc::now();
        let mut store = self.inner.write().expect("conversation lock poisoned");

        let inherited_project = request
            .current_context
            .as_ref()
            .and_then(|current| store.conversations.get(current))
            .and_then(|state| state.project_name.clone());

        let context_id = request.new_context.unwrap_or_else(|| Uuid::new_v4().to_string());
        if !store.conversations.contains_key(&context_id) {
            store.next_no += 1;
            let next_no = store.next_no;
            store.conversations.insert(
                context_id.clone(),
                ConversationState {
                    id: context_id.clone(),
                    no: next_no,
                    name: None,
                    project_name: inherited_project,
                    created_at: now,
                    last_message: now,
                    expires_at: now + Duration::hours(24),
                    paused: false,
                    running: false,
                    items: Vec::new(),
                },
            );
        }

        Ok(CreateContextResponse {
            ok: true,
            ctxid: context_id,
            message: "Context created.".to_string(),
        })
    }

    async fn build_state_snapshot(
        &self,
        request: StateSnapshotRequest,
    ) -> Result<StateSnapshot, AppError> {
        self.prune_expired();

        let store = self.inner.read().expect("conversation lock poisoned");
        let active_context =
            request.context.as_ref().and_then(|context_id| store.conversations.get(context_id));

        let mut contexts =
            store.conversations.values().cloned().map(to_context_entry).collect::<Vec<_>>();
        contexts.sort_by(|left, right| right.created_at.cmp(&left.created_at));

        let logs = if let Some(active_context) = active_context {
            active_context
                .items
                .iter()
                .skip(request.log_from)
                .map(|item| {
                    json!({
                        "index": item.index,
                        "role": item.role,
                        "content": item.content,
                        "attachments": item.attachments,
                        "created_at": item.created_at,
                    })
                })
                .collect::<Vec<_>>()
        } else {
            Vec::new()
        };

        Ok(StateSnapshot {
            deselect_chat: request.context.is_some() && active_context.is_none(),
            context: active_context.map(|state| state.id.clone()).unwrap_or_default(),
            contexts,
            tasks: Vec::new(),
            logs,
            log_guid: active_context.map(|state| state.id.clone()).unwrap_or_default(),
            log_version: active_context.map(|state| state.items.len()).unwrap_or(0),
            log_progress: if active_context.is_some() { json!("") } else { json!(0) },
            log_progress_active: false,
            paused: active_context.map(|state| state.paused).unwrap_or(false),
            notifications: Vec::new(),
            notifications_guid: "notifications".to_string(),
            notifications_version: request.notifications_from,
        })
    }
}

impl InMemoryConversationService {
    fn prune_expired(&self) {
        let now = Utc::now();
        self.inner
            .write()
            .expect("conversation lock poisoned")
            .conversations
            .retain(|_, state| state.expires_at > now);
    }
}

fn to_context_entry(state: ConversationState) -> UiContextEntry {
    UiContextEntry {
        id: state.id.clone(),
        name: state.name,
        created_at: state.created_at,
        no: state.no,
        log_guid: state.id.clone(),
        log_version: state.items.len(),
        log_length: state.items.len(),
        paused: state.paused,
        last_message: state.last_message,
        kind: "user".to_string(),
        running: state.running,
        project: state.project_name,
    }
}

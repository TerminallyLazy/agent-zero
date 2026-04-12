use std::{
    collections::HashMap,
    sync::{Arc, RwLock},
};

use async_trait::async_trait;
use chrono::{DateTime, Duration, Utc};
use uuid::Uuid;

use crate::{
    AppError, ConversationLog, ConversationLogItem, ConversationService, SendMessageRequest,
    SendMessageResponse,
};

#[derive(Debug, Default, Clone)]
pub struct InMemoryConversationService {
    inner: Arc<RwLock<HashMap<String, ConversationState>>>,
}

#[derive(Debug, Clone)]
struct ConversationState {
    id: String,
    project_name: Option<String>,
    expires_at: DateTime<Utc>,
    items: Vec<ConversationLogItem>,
}

#[async_trait]
impl ConversationService for InMemoryConversationService {
    async fn send_external_message(
        &self,
        request: SendMessageRequest,
    ) -> Result<SendMessageResponse, AppError> {
        self.prune_expired();

        if request.message.trim().is_empty() {
            return Err(AppError::InvalidRequest("message is required".to_string()));
        }

        let now = Utc::now();
        let mut store = self.inner.write().expect("conversation lock poisoned");

        let state = match request.context_id.clone() {
            Some(context_id) => {
                let state = store
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
                store.entry(context_id.clone()).or_insert_with(|| ConversationState {
                    id: context_id,
                    project_name: request.project_name.clone(),
                    expires_at: now + Duration::hours(request.lifetime_hours as i64),
                    items: Vec::new(),
                })
            }
        };

        state.expires_at = now + Duration::hours(request.lifetime_hours as i64);

        let user_index = state.items.len();
        state.items.push(ConversationLogItem {
            index: user_index,
            role: "user".to_string(),
            content: request.message.clone(),
            attachments: request.attachment_filenames.clone(),
            created_at: now,
        });

        let mut response = format!("Rust skeleton received: {}", request.message);
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
}

impl InMemoryConversationService {
    fn prune_expired(&self) {
        let now = Utc::now();
        self.inner
            .write()
            .expect("conversation lock poisoned")
            .retain(|_, state| state.expires_at > now);
    }
}

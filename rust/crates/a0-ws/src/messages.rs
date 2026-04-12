use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerEnvelope {
    pub event: String,
    #[serde(rename = "eventId")]
    pub event_id: Uuid,
    #[serde(rename = "correlationId")]
    pub correlation_id: Option<Uuid>,
    #[serde(rename = "handlerId")]
    pub handler_id: String,
    pub ts: DateTime<Utc>,
    pub data: Value,
}

impl ServerEnvelope {
    pub fn new(
        event: impl Into<String>,
        handler_id: impl Into<String>,
        data: Value,
        correlation_id: Option<Uuid>,
    ) -> Self {
        Self {
            event: event.into(),
            event_id: Uuid::new_v4(),
            correlation_id,
            handler_id: handler_id.into(),
            ts: Utc::now(),
            data,
        }
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct ClientEnvelope {
    pub event: String,
    #[serde(rename = "correlationId")]
    pub correlation_id: Option<Uuid>,
    #[serde(default)]
    pub data: Value,
}

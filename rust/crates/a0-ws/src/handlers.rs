use a0_core::AppError;
use serde_json::json;

use crate::messages::{ClientEnvelope, ServerEnvelope};

pub fn handle_client_message(input: &str) -> Result<ServerEnvelope, AppError> {
    let message: ClientEnvelope =
        serde_json::from_str(input).map_err(|error| AppError::InvalidRequest(error.to_string()))?;

    let envelope = match message.event.as_str() {
        "hello" => ServerEnvelope::new(
            "hello",
            "rust.stub.health",
            json!({"ok": true, "message": "hello", "echo": message.data}),
            message.correlation_id,
        ),
        "ping" => ServerEnvelope::new(
            "ping",
            "rust.stub.health",
            json!({"ok": true, "message": "pong", "echo": message.data}),
            message.correlation_id,
        ),
        _ => ServerEnvelope::new(
            "not_implemented",
            "rust.stub.health",
            json!({"ok": false, "code": "not_implemented", "message": "event is not implemented"}),
            message.correlation_id,
        ),
    };

    Ok(envelope)
}

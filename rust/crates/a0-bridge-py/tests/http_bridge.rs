use std::time::Duration;

use axum::{
    extract::{Query, State},
    routing::{get, post},
    Json, Router,
};
use serde::{Deserialize, Serialize};

use a0_bridge_py::{HttpBridge, HttpConversationService};
use a0_config::BridgeSettings;
use a0_core::{BridgeService, ConversationService, SendMessageRequest};

#[derive(Clone, Default)]
struct MockState;

#[derive(Debug, Deserialize)]
struct MockMessageRequest {
    context_id: Option<String>,
    message: String,
}

#[derive(Debug, Deserialize)]
struct MockLogQuery {
    context_id: String,
    length: usize,
}

#[derive(Debug, Serialize)]
struct MockMessageResponse {
    context_id: String,
    response: String,
}

#[derive(Debug, Serialize)]
struct MockLogItem {
    index: usize,
    role: String,
    content: String,
    attachments: Vec<String>,
    created_at: String,
}

#[derive(Debug, Serialize)]
struct MockLog {
    context_id: String,
    guid: String,
    total_items: usize,
    returned_items: usize,
    start_position: usize,
    progress: Option<String>,
    progress_active: bool,
    items: Vec<MockLogItem>,
}

#[derive(Debug, Serialize)]
struct MockLogResponse {
    context_id: String,
    log: MockLog,
}

#[tokio::test]
async fn http_conversation_service_delegates_message_and_log_calls() {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    let app = Router::new()
        .route("/health", get(|| async { Json(serde_json::json!({"ok": true})) }))
        .route("/api_message", post(mock_api_message))
        .route("/api_log_get", get(mock_api_log_get))
        .with_state(MockState);

    let server = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });

    tokio::time::sleep(Duration::from_millis(50)).await;

    let settings = BridgeSettings {
        mode: "http".to_string(),
        base_url: Some(format!("http://{addr}")),
        api_key: Some("secret".to_string()),
        timeout_secs: 5,
    };

    let bridge = HttpBridge::new(settings.clone()).unwrap();
    bridge.ready().await.unwrap();

    let service = HttpConversationService::new(settings).unwrap();
    let sent = service
        .send_external_message(SendMessageRequest {
            context_id: None,
            message: "bridge hello".to_string(),
            attachment_filenames: Vec::new(),
            lifetime_hours: 24,
            project_name: None,
        })
        .await
        .unwrap();

    assert_eq!(sent.context_id, "ctx-123");
    assert!(sent.response.contains("bridge hello"));

    let log = service.get_log("ctx-123", 10).await.unwrap();
    assert_eq!(log.returned_items, 2);
    assert_eq!(log.items[0].role, "user");
    assert_eq!(log.items[1].role, "assistant");

    server.abort();
}

async fn mock_api_message(
    State(_state): State<MockState>,
    Json(payload): Json<MockMessageRequest>,
) -> Json<MockMessageResponse> {
    Json(MockMessageResponse {
        context_id: payload.context_id.unwrap_or_else(|| "ctx-123".to_string()),
        response: format!("python bridge replied to {}", payload.message),
    })
}

async fn mock_api_log_get(
    State(_state): State<MockState>,
    Query(query): Query<MockLogQuery>,
) -> Json<MockLogResponse> {
    Json(MockLogResponse {
        context_id: query.context_id.clone(),
        log: MockLog {
            context_id: query.context_id.clone(),
            guid: query.context_id,
            total_items: 2,
            returned_items: 2.min(query.length),
            start_position: 0,
            progress: None,
            progress_active: false,
            items: vec![
                MockLogItem {
                    index: 0,
                    role: "user".to_string(),
                    content: "bridge hello".to_string(),
                    attachments: Vec::new(),
                    created_at: "2026-04-12T23:00:00Z".to_string(),
                },
                MockLogItem {
                    index: 1,
                    role: "assistant".to_string(),
                    content: "python bridge replied to bridge hello".to_string(),
                    attachments: Vec::new(),
                    created_at: "2026-04-12T23:00:00Z".to_string(),
                },
            ],
        },
    })
}

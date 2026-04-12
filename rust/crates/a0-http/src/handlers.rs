use std::sync::Arc;

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Json, Query, State,
    },
    http::HeaderMap,
    response::IntoResponse,
};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::sync::mpsc;
use uuid::Uuid;

use a0_core::{
    AppError, BridgeService, ConversationService, InMemoryConversationService, PluginSummary,
    SendMessageRequest,
};
use a0_observability::build_info;
use a0_ws::{handlers::handle_client_message, messages::ServerEnvelope};

use crate::{
    error::HttpError,
    models::{
        ApiLogQuery, ApiLogResponse, ApiMessageRequest, ApiMessageResponse, PluginListResponse,
        ReadyResponse, SettingsResponse, SuccessEnvelope, VersionResponse,
    },
    AppState,
};

pub async fn health(
    headers: HeaderMap,
    State(state): State<AppState>,
) -> Json<SuccessEnvelope<Value>> {
    let request_id = request_id(&headers);
    let snapshot = state.health.live();
    Json(SuccessEnvelope {
        ok: true,
        request_id,
        data: json!({"status": snapshot.status, "ready": snapshot.ready, "components": snapshot.components}),
    })
}

pub async fn ready(
    headers: HeaderMap,
    State(state): State<AppState>,
) -> Json<SuccessEnvelope<ReadyResponse>> {
    let request_id = request_id(&headers);
    let snapshot = state.health.ready();
    Json(SuccessEnvelope { ok: snapshot.ok, request_id, data: snapshot.into() })
}

pub async fn version(headers: HeaderMap) -> Json<SuccessEnvelope<VersionResponse>> {
    let request_id = request_id(&headers);
    Json(SuccessEnvelope { ok: true, request_id, data: build_info().into() })
}

pub async fn api_message(
    headers: HeaderMap,
    State(state): State<AppState>,
    Json(payload): Json<ApiMessageRequest>,
) -> Result<Json<ApiMessageResponse>, HttpError> {
    let request_id = request_id(&headers);

    let attachment_filenames = payload
        .attachments
        .unwrap_or_default()
        .into_iter()
        .map(|attachment| {
            let _ = base64::engine::general_purpose::STANDARD
                .decode(attachment.base64.as_bytes())
                .map_err(|error| {
                    HttpError::new(
                        axum::http::StatusCode::BAD_REQUEST,
                        "invalid_request",
                        error.to_string(),
                        request_id.clone(),
                    )
                })?;
            Ok(attachment.filename)
        })
        .collect::<Result<Vec<_>, HttpError>>()?;

    let result = state
        .conversations
        .send_external_message(SendMessageRequest {
            context_id: payload.context_id,
            message: payload.message,
            attachment_filenames,
            lifetime_hours: payload.lifetime_hours.unwrap_or(24),
            project_name: payload.project_name,
        })
        .await
        .map_err(|error| map_app_error(error, request_id))?;

    Ok(Json(ApiMessageResponse { context_id: result.context_id, response: result.response }))
}

pub async fn api_plugins(headers: HeaderMap) -> Json<SuccessEnvelope<PluginListResponse>> {
    let request_id = request_id(&headers);
    Json(SuccessEnvelope {
        ok: true,
        request_id,
        data: PluginListResponse {
            plugins: vec![PluginSummary { name: "rust-skeleton".to_string(), enabled: true }],
        },
    })
}

pub async fn api_settings(
    headers: HeaderMap,
    State(state): State<AppState>,
) -> Json<SuccessEnvelope<SettingsResponse>> {
    let request_id = request_id(&headers);
    Json(SuccessEnvelope {
        ok: true,
        request_id,
        data: SettingsResponse {
            server_host: state.settings.server.host.clone(),
            server_port: state.settings.server.port,
            bridge_mode: state.bridge.mode().await.to_string(),
        },
    })
}

pub async fn api_log_get(
    headers: HeaderMap,
    State(state): State<AppState>,
    Query(query): Query<ApiLogQuery>,
) -> Result<Json<ApiLogResponse>, HttpError> {
    api_log_get_inner(headers, state, query).await
}

pub async fn api_log_post(
    headers: HeaderMap,
    State(state): State<AppState>,
    Json(query): Json<ApiLogQuery>,
) -> Result<Json<ApiLogResponse>, HttpError> {
    api_log_get_inner(headers, state, query).await
}

async fn api_log_get_inner(
    headers: HeaderMap,
    state: AppState,
    query: ApiLogQuery,
) -> Result<Json<ApiLogResponse>, HttpError> {
    let request_id = request_id(&headers);
    let context_id = query.context_id.ok_or_else(|| {
        HttpError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "invalid_request",
            "context_id is required",
            request_id.clone(),
        )
    })?;

    let log = state
        .conversations
        .get_log(&context_id, query.length.unwrap_or(100))
        .await
        .map_err(|error| map_app_error(error, request_id))?;

    Ok(Json(ApiLogResponse { context_id, log }))
}

pub async fn websocket_upgrade(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, state))
}

async fn handle_socket(socket: WebSocket, state: AppState) {
    let connection_id = Uuid::new_v4().to_string();
    let (mut sender, mut receiver) = socket.split();
    let (tx, mut rx) = mpsc::unbounded_channel::<String>();

    state.ws_hub.register(connection_id.clone(), tx).await;

    let hello = ServerEnvelope::new(
        "hello",
        "rust.stub.health",
        json!({"ok": true, "message": "connected", "connectionId": connection_id}),
        None,
    );
    if let Ok(payload) = serde_json::to_string(&hello) {
        let _ = sender.send(Message::Text(payload.into())).await;
    }

    loop {
        tokio::select! {
            Some(outgoing) = rx.recv() => {
                if sender.send(Message::Text(outgoing.into())).await.is_err() {
                    break;
                }
            }
            Some(message) = receiver.next() => {
                match message {
                    Ok(Message::Text(text)) => {
                        let response = match handle_client_message(&text) {
                            Ok(envelope) => envelope,
                            Err(error) => ServerEnvelope::new(
                                "error",
                                "rust.stub.health",
                                json!({"ok": false, "code": error.code(), "message": error.to_string()}),
                                None,
                            ),
                        };
                        if let Ok(payload) = serde_json::to_string(&response) {
                            if sender.send(Message::Text(payload.into())).await.is_err() {
                                break;
                            }
                        }
                    }
                    Ok(Message::Close(_)) => break,
                    Ok(_) => {}
                    Err(_) => break,
                }
            }
            else => break,
        }
    }

    state.ws_hub.unregister(&connection_id).await;
}

fn request_id(headers: &HeaderMap) -> String {
    headers
        .get("x-request-id")
        .and_then(|value| value.to_str().ok())
        .map(ToString::to_string)
        .unwrap_or_else(|| Uuid::new_v4().to_string())
}

pub fn default_bridge() -> Arc<dyn BridgeService> {
    Arc::new(a0_bridge_py::NullBridge)
}

pub fn default_conversations() -> Arc<dyn ConversationService> {
    Arc::new(InMemoryConversationService::default())
}

fn map_app_error(error: AppError, request_id: String) -> HttpError {
    HttpError::from_app_error(error, request_id)
}

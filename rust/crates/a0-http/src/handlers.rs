use std::sync::Arc;

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        State,
    },
    http::HeaderMap,
    response::IntoResponse,
    Json,
};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::sync::mpsc;
use uuid::Uuid;

use a0_core::{AppError, BridgeService, PluginSummary};
use a0_observability::build_info;
use a0_ws::{handlers::handle_client_message, messages::ServerEnvelope};

use crate::{
    error::HttpError,
    models::{
        PluginListResponse, ReadyResponse, SettingsResponse, SuccessEnvelope, VersionResponse,
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

pub async fn api_message(headers: HeaderMap) -> Result<Json<SuccessEnvelope<Value>>, HttpError> {
    Err(HttpError::from_app_error(
        AppError::NotImplemented("POST /api/message"),
        request_id(&headers),
    ))
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

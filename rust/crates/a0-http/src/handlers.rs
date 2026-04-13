use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    sync::Arc,
};

use axum::{
    extract::{
        multipart::Multipart,
        ws::{Message, WebSocket, WebSocketUpgrade},
        FromRequest, Json, Query, Request, State,
    },
    http::HeaderMap,
    response::{Html, IntoResponse},
};
use base64::Engine;
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use tokio::sync::mpsc;
use uuid::Uuid;

use a0_core::{
    AppError, BridgeService, ConversationService, CreateContextRequest, CreateContextResponse,
    InMemoryConversationService, PluginSummary, SendMessageRequest, StateSnapshot,
    StateSnapshotRequest,
};
use a0_observability::build_info;
use a0_ws::{handlers::handle_client_message, messages::ServerEnvelope};

use crate::{
    error::HttpError,
    models::{
        ActionResponse, AgentsRequest, ApiLogQuery, ApiLogResponse, ApiMessageRequest,
        ApiMessageResponse, CsrfTokenResponse, LoadWebuiExtensionsRequest,
        LoadWebuiExtensionsResponse, PluginListResponse, ProjectsRequest, ReadyResponse,
        SettingsResponse, SuccessEnvelope, UiMessageRequest, UiMessageResponse, VersionResponse,
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

pub async fn ui_index(State(state): State<AppState>) -> Result<Html<String>, HttpError> {
    let index_path = state.ui_asset_root.join("index.html");
    let template = tokio::fs::read_to_string(&index_path).await.map_err(|error| {
        HttpError::new(
            axum::http::StatusCode::INTERNAL_SERVER_ERROR,
            "ui_asset_missing",
            format!("failed to read web UI shell from {}: {error}", index_path.display()),
            Uuid::new_v4().to_string(),
        )
    })?;

    Ok(Html(render_index_template(&template, &state)))
}

pub async fn load_webui_extensions(
    State(state): State<AppState>,
    Json(payload): Json<LoadWebuiExtensionsRequest>,
) -> Json<LoadWebuiExtensionsResponse> {
    Json(LoadWebuiExtensionsResponse {
        extensions: discover_webui_extensions(
            &state.workspace_root,
            &payload.extension_point,
            payload.filters.as_deref().unwrap_or(&["*".to_string()]),
        ),
    })
}

pub async fn settings_get(State(state): State<AppState>) -> Json<Value> {
    Json(build_settings_payload(&state.workspace_root))
}

pub async fn projects(
    State(state): State<AppState>,
    Json(payload): Json<ProjectsRequest>,
) -> Json<ActionResponse> {
    let response = match payload.action.as_deref().unwrap_or_default() {
        "list" => ActionResponse {
            ok: true,
            data: Some(Value::Array(load_projects_list(&state.workspace_root))),
            error: None,
        },
        "list_options" => ActionResponse {
            ok: true,
            data: Some(Value::Array(load_projects_list_options(&state.workspace_root))),
            error: None,
        },
        _ => ActionResponse { ok: false, data: None, error: Some("Invalid action".to_string()) },
    };

    Json(response)
}

pub async fn agents(
    State(state): State<AppState>,
    Json(payload): Json<AgentsRequest>,
) -> Json<ActionResponse> {
    let response = match payload.action.as_deref().unwrap_or_default() {
        "list" => ActionResponse {
            ok: true,
            data: Some(Value::Array(load_agents_list(&state.workspace_root))),
            error: None,
        },
        _ => ActionResponse { ok: false, data: None, error: Some("Invalid action".to_string()) },
    };

    Json(response)
}

pub async fn api_csrf_token(State(state): State<AppState>) -> Json<CsrfTokenResponse> {
    Json(CsrfTokenResponse {
        ok: true,
        token: Uuid::new_v4().to_string(),
        runtime_id: state.runtime_id,
    })
}

pub async fn ui_message(
    State(state): State<AppState>,
    request: Request,
) -> Result<Json<UiMessageResponse>, HttpError> {
    handle_ui_message(state, request, false).await
}

pub async fn ui_message_async(
    State(state): State<AppState>,
    request: Request,
) -> Result<Json<UiMessageResponse>, HttpError> {
    handle_ui_message(state, request, true).await
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

pub async fn api_chat_create(
    headers: HeaderMap,
    State(state): State<AppState>,
    Json(payload): Json<CreateContextRequest>,
) -> Result<Json<CreateContextResponse>, HttpError> {
    let request_id = request_id(&headers);
    let response = state
        .conversations
        .create_context(payload)
        .await
        .map_err(|error| map_app_error(error, request_id))?;

    Ok(Json(response))
}

pub async fn api_poll(
    headers: HeaderMap,
    State(state): State<AppState>,
    Json(payload): Json<StateSnapshotRequest>,
) -> Result<Json<StateSnapshot>, HttpError> {
    let request_id = request_id(&headers);
    let response = state
        .conversations
        .build_state_snapshot(payload)
        .await
        .map_err(|error| map_app_error(error, request_id))?;

    Ok(Json(response))
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

async fn handle_ui_message(
    state: AppState,
    request: Request,
    acknowledge_only: bool,
) -> Result<Json<UiMessageResponse>, HttpError> {
    let request_id = request_id(request.headers());
    let payload = parse_ui_message_request(request, state.clone(), request_id.clone()).await?;

    let result = state
        .conversations
        .send_external_message(SendMessageRequest {
            context_id: payload.context_id,
            message: payload.message,
            attachment_filenames: payload.attachment_filenames,
            lifetime_hours: 24,
            project_name: None,
        })
        .await
        .map_err(|error| map_app_error(error, request_id))?;

    let message = if acknowledge_only { "Message received.".to_string() } else { result.response };

    Ok(Json(UiMessageResponse { message, context: result.context_id }))
}

async fn parse_ui_message_request(
    request: Request,
    state: AppState,
    request_id: String,
) -> Result<ParsedUiMessageRequest, HttpError> {
    let content_type = request
        .headers()
        .get(http::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_ascii_lowercase();

    if content_type.starts_with("multipart/form-data") {
        let mut multipart = Multipart::from_request(request, &state).await.map_err(|error| {
            HttpError::new(
                axum::http::StatusCode::BAD_REQUEST,
                "invalid_request",
                error.body_text(),
                request_id.clone(),
            )
        })?;

        let mut message = None;
        let mut context_id = None;
        let mut attachment_filenames = Vec::new();

        while let Some(field) = multipart.next_field().await.map_err(|error| {
            HttpError::new(
                axum::http::StatusCode::BAD_REQUEST,
                "invalid_request",
                error.to_string(),
                request_id.clone(),
            )
        })? {
            match field.name() {
                Some("text") => {
                    message = Some(field.text().await.map_err(|error| {
                        HttpError::new(
                            axum::http::StatusCode::BAD_REQUEST,
                            "invalid_request",
                            error.to_string(),
                            request_id.clone(),
                        )
                    })?);
                }
                Some("context") => {
                    context_id = Some(field.text().await.map_err(|error| {
                        HttpError::new(
                            axum::http::StatusCode::BAD_REQUEST,
                            "invalid_request",
                            error.to_string(),
                            request_id.clone(),
                        )
                    })?);
                }
                Some("attachments") => {
                    if let Some(filename) = field.file_name().map(ToString::to_string) {
                        attachment_filenames.push(filename);
                    }
                }
                _ => {}
            }
        }

        return build_ui_message_request(message, context_id, attachment_filenames, request_id);
    }

    let Json(payload) =
        Json::<UiMessageRequest>::from_request(request, &state).await.map_err(|error| {
            HttpError::new(
                axum::http::StatusCode::BAD_REQUEST,
                "invalid_request",
                error.body_text(),
                request_id.clone(),
            )
        })?;

    build_ui_message_request(payload.text, payload.context, Vec::new(), request_id)
}

fn build_ui_message_request(
    message: Option<String>,
    context_id: Option<String>,
    attachment_filenames: Vec<String>,
    request_id: String,
) -> Result<ParsedUiMessageRequest, HttpError> {
    let message = message.unwrap_or_default().trim().to_string();
    if message.is_empty() && attachment_filenames.is_empty() {
        return Err(HttpError::new(
            axum::http::StatusCode::BAD_REQUEST,
            "invalid_request",
            "text is required",
            request_id,
        ));
    }

    Ok(ParsedUiMessageRequest {
        message,
        context_id: normalize_optional_string(context_id),
        attachment_filenames,
    })
}

fn normalize_optional_string(value: Option<String>) -> Option<String> {
    value.and_then(|value| {
        let trimmed = value.trim();
        if trimmed.is_empty() || trimmed.eq_ignore_ascii_case("null") {
            None
        } else {
            Some(trimmed.to_string())
        }
    })
}

fn render_index_template(template: &str, state: &AppState) -> String {
    let version = state.build_info.version.as_str();
    let version_time = state.build_info.commit.as_deref().unwrap_or("rust-dev");
    let runtime_is_development = if cfg!(debug_assertions) { "true" } else { "false" };

    template
        .replace("{{version_no}}", version)
        .replace("{{version_time}}", version_time)
        .replace("{{runtime_id}}", &state.runtime_id)
        .replace("{{runtime_is_development}}", runtime_is_development)
        .replace("{{logged_in}}", "false")
}

fn discover_webui_extensions(
    workspace_root: &Path,
    extension_point: &str,
    filters: &[String],
) -> Vec<String> {
    let mut matches = Vec::new();
    let effective_filters =
        if filters.is_empty() { vec!["*".to_string()] } else { filters.to_vec() };

    for root in extension_roots(workspace_root, extension_point) {
        let read_dir = match std::fs::read_dir(&root) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        for entry in read_dir.flatten() {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            let Some(file_name) = path.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            if !effective_filters.iter().any(|filter| matches_filter(file_name, filter)) {
                continue;
            }
            if let Ok(relative) = path.strip_prefix(workspace_root) {
                matches.push(relative.to_string_lossy().replace('\\', "/"));
            }
        }
    }

    matches.sort();
    matches.dedup();
    matches
}

fn extension_roots(workspace_root: &Path, extension_point: &str) -> Vec<PathBuf> {
    let mut roots = vec![workspace_root.join("extensions/webui").join(extension_point)];

    for container in [
        workspace_root.join("plugins"),
        workspace_root.join("usr/plugins"),
        workspace_root.join("agents"),
        workspace_root.join("usr/agents"),
    ] {
        let Ok(entries) = std::fs::read_dir(container) else {
            continue;
        };
        for entry in entries.flatten() {
            let path = entry.path().join("extensions/webui").join(extension_point);
            roots.push(path);
        }
    }

    roots
}

fn matches_filter(file_name: &str, filter: &str) -> bool {
    if filter == "*" {
        return true;
    }
    if let Some(suffix) = filter.strip_prefix('*') {
        return file_name.ends_with(suffix);
    }
    file_name == filter
}

fn build_settings_payload(workspace_root: &Path) -> Value {
    let settings_path = workspace_root.join("usr/settings.json");
    let mut settings = std::fs::read_to_string(&settings_path)
        .ok()
        .and_then(|contents| serde_json::from_str::<Value>(&contents).ok())
        .unwrap_or_else(|| json!({}));

    if let Some(map) = settings.as_object_mut() {
        set_default_string(map, "stt_model_size", "base");
        set_default_string(map, "stt_language", "en");
        set_default_value(map, "stt_silence_threshold", json!(0.3));
        set_default_value(map, "stt_silence_duration", json!(1000));
        set_default_value(map, "stt_waiting_timeout", json!(2000));
        map.entry("tts_kokoro").or_insert(Value::Bool(true));
    }

    json!({
        "settings": settings,
        "additional": {
            "chat_providers": [],
            "embedding_providers": [],
            "is_dockerized": false,
            "agent_subdirs": load_agents_list(workspace_root).into_iter().map(|entry| {
                json!({
                    "value": entry["key"].clone(),
                    "label": entry["label"].clone(),
                })
            }).collect::<Vec<_>>(),
            "knowledge_subdirs": load_knowledge_subdirs(workspace_root),
            "stt_models": [
                {"value": "tiny", "label": "Tiny (39M, English)"},
                {"value": "base", "label": "Base (74M, English)"},
                {"value": "small", "label": "Small (244M, English)"},
                {"value": "medium", "label": "Medium (769M, English)"},
                {"value": "large", "label": "Large (1.5B, Multilingual)"},
                {"value": "turbo", "label": "Turbo (Multilingual)"}
            ],
            "runtime_settings": {
                "uvicorn_access_logs_enabled": false
            }
        }
    })
}

fn set_default_string(map: &mut serde_json::Map<String, Value>, key: &str, default: &str) {
    map.entry(key.to_string()).or_insert_with(|| Value::String(default.to_string()));
}

fn set_default_value(map: &mut serde_json::Map<String, Value>, key: &str, default: Value) {
    map.entry(key.to_string()).or_insert(default);
}

fn load_projects_list(workspace_root: &Path) -> Vec<Value> {
    let parent = workspace_root.join("usr/projects");
    let Ok(entries) = std::fs::read_dir(parent) else {
        return Vec::new();
    };

    let mut projects = Vec::new();
    for entry in entries.flatten() {
        let project_dir = entry.path();
        if !project_dir.is_dir() {
            continue;
        }
        let Some(name) = project_dir.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        let data = load_project_metadata(&project_dir);
        projects.push(json!({
            "name": name,
            "title": data.get("title").and_then(Value::as_str).unwrap_or(name),
            "description": data.get("description").and_then(Value::as_str).unwrap_or(""),
            "color": data.get("color").and_then(Value::as_str).unwrap_or(""),
        }));
    }

    projects.sort_by(|left, right| left["name"].as_str().cmp(&right["name"].as_str()));
    projects
}

fn load_projects_list_options(workspace_root: &Path) -> Vec<Value> {
    load_projects_list(workspace_root)
        .into_iter()
        .filter_map(|project| {
            let key = project.get("name")?.as_str()?.to_string();
            let label = project
                .get("title")
                .and_then(Value::as_str)
                .filter(|value| !value.is_empty())
                .unwrap_or(&key)
                .to_string();
            Some(json!({ "key": key, "label": label }))
        })
        .collect()
}

fn load_project_metadata(project_dir: &Path) -> Value {
    let path = project_dir.join(".a0proj/project.json");
    std::fs::read_to_string(path)
        .ok()
        .and_then(|contents| serde_json::from_str::<Value>(&contents).ok())
        .unwrap_or_else(|| json!({}))
}

fn load_agents_list(workspace_root: &Path) -> Vec<Value> {
    let mut merged = BTreeMap::new();

    for container in [workspace_root.join("agents"), workspace_root.join("usr/agents")] {
        let Ok(entries) = std::fs::read_dir(container) else {
            continue;
        };
        for entry in entries.flatten() {
            let agent_dir = entry.path();
            if !agent_dir.is_dir() {
                continue;
            }
            let Some(key) = agent_dir.file_name().and_then(|value| value.to_str()) else {
                continue;
            };
            let label = load_agent_title(&agent_dir).unwrap_or_else(|| key.to_string());
            merged.entry(key.to_string()).or_insert_with(|| label);
        }
    }

    merged.into_iter().map(|(key, label)| json!({ "key": key, "label": label })).collect()
}

fn load_agent_title(agent_dir: &Path) -> Option<String> {
    let path = agent_dir.join("agent.yaml");
    let contents = std::fs::read_to_string(path).ok()?;
    contents.lines().find_map(|line| {
        let trimmed = line.trim();
        trimmed
            .strip_prefix("title:")
            .map(|value| value.trim().trim_matches('"').to_string())
            .filter(|value| !value.is_empty())
    })
}

fn load_knowledge_subdirs(workspace_root: &Path) -> Vec<Value> {
    let Ok(entries) = std::fs::read_dir(workspace_root.join("knowledge")) else {
        return Vec::new();
    };

    let mut subdirs = Vec::new();
    for entry in entries.flatten() {
        let path = entry.path();
        if !path.is_dir() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|value| value.to_str()) else {
            continue;
        };
        if name == "default" {
            continue;
        }
        subdirs.push(json!({ "value": name, "label": name }));
    }

    subdirs.sort_by(|left, right| left["value"].as_str().cmp(&right["value"].as_str()));
    subdirs
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

struct ParsedUiMessageRequest {
    message: String,
    context_id: Option<String>,
    attachment_filenames: Vec<String>,
}

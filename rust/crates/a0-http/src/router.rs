use axum::{
    http::{HeaderValue, Method},
    routing::{get, get_service, post},
    Router,
};
use tower_http::{
    cors::{Any, CorsLayer},
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer},
    services::ServeDir,
    trace::TraceLayer,
};

use crate::{handlers, AppState};

pub fn build_router(state: AppState) -> Router {
    let ui_assets = state.ui_asset_root.clone();
    let plugin_assets = state.workspace_root.join("plugins");
    let user_plugin_assets = state.workspace_root.join("usr/plugins");
    let extension_assets = state.workspace_root.join("extensions/webui");

    Router::new()
        .route("/", get(handlers::ui_index))
        .route("/health", get(handlers::health))
        .route("/ready", get(handlers::ready))
        .route("/version", get(handlers::version))
        .route("/api/load_webui_extensions", post(handlers::load_webui_extensions))
        .route("/api/settings_get", get(handlers::settings_get).post(handlers::settings_get))
        .route("/api/projects", post(handlers::projects))
        .route("/api/agents", post(handlers::agents))
        .route("/api/csrf_token", get(handlers::api_csrf_token))
        .route("/message", post(handlers::ui_message))
        .route("/message_async", post(handlers::ui_message_async))
        .route("/api/message", post(handlers::api_message))
        .route("/api_message", post(handlers::api_message))
        .route("/api/plugins", get(handlers::api_plugins))
        .route("/api/settings", get(handlers::api_settings))
        .route("/api/chat_create", post(handlers::api_chat_create))
        .route("/api_log_get", get(handlers::api_log_get).post(handlers::api_log_post))
        .route("/api/poll", post(handlers::api_poll))
        .route("/ws", get(handlers::websocket_upgrade))
        .nest_service("/plugins", get_service(ServeDir::new(plugin_assets)))
        .nest_service("/usr/plugins", get_service(ServeDir::new(user_plugin_assets)))
        .nest_service("/extensions/webui", get_service(ServeDir::new(extension_assets)))
        .fallback_service(get_service(ServeDir::new(ui_assets)))
        .layer(PropagateRequestIdLayer::x_request_id())
        .layer(SetRequestIdLayer::x_request_id(MakeRequestUuid))
        .layer(TraceLayer::new_for_http())
        .layer(cors_layer(&state.settings.security.allowed_origins))
        .with_state(state)
}

fn cors_layer(allowed_origins: &[String]) -> CorsLayer {
    if allowed_origins.is_empty() || allowed_origins.iter().any(|origin| origin == "*") {
        return CorsLayer::new().allow_origin(Any).allow_methods([Method::GET, Method::POST]);
    }

    let headers: Vec<HeaderValue> =
        allowed_origins.iter().filter_map(|origin| HeaderValue::from_str(origin).ok()).collect();

    CorsLayer::new().allow_origin(headers).allow_methods([Method::GET, Method::POST])
}

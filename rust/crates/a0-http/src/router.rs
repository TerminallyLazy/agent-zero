use axum::{
    http::{HeaderValue, Method},
    routing::{get, post},
    Router,
};
use tower_http::{
    cors::{Any, CorsLayer},
    request_id::{MakeRequestUuid, PropagateRequestIdLayer, SetRequestIdLayer},
    trace::TraceLayer,
};

use crate::{handlers, AppState};

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(handlers::health))
        .route("/ready", get(handlers::ready))
        .route("/version", get(handlers::version))
        .route("/api/message", post(handlers::api_message))
        .route("/api_message", post(handlers::api_message))
        .route("/api/plugins", get(handlers::api_plugins))
        .route("/api/settings", get(handlers::api_settings))
        .route("/api_log_get", get(handlers::api_log_get).post(handlers::api_log_post))
        .route("/ws", get(handlers::websocket_upgrade))
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

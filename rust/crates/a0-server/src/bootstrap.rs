use std::sync::Arc;

use anyhow::Result;

use a0_bridge_py::NullBridge;
use a0_config::Settings;
use a0_core::InMemoryConversationService;
use a0_http::{build_router, AppState};
use a0_observability::HealthRegistry;

pub async fn serve(settings: Settings) -> Result<()> {
    let health = HealthRegistry::new();
    health.set_component("bridge", true, "null bridge ready");
    health.set_component("router", true, "http and websocket routes registered");

    let state = AppState::new(
        settings.clone(),
        health,
        Arc::new(NullBridge),
        Arc::new(InMemoryConversationService::default()),
    );
    let app = build_router(state);
    let listener =
        tokio::net::TcpListener::bind((settings.server.host.as_str(), settings.server.port))
            .await?;

    tracing::info!(
        host = %settings.server.host,
        port = settings.server.port,
        "starting rust backend skeleton"
    );

    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;

    Ok(())
}

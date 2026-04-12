use std::sync::Arc;

use anyhow::Result;

use a0_bridge_py::{HttpBridge, HttpConversationService, NullBridge};
use a0_config::Settings;
use a0_core::{BridgeService, ConversationService, InMemoryConversationService};
use a0_http::{build_router, AppState};
use a0_observability::HealthRegistry;

pub async fn serve(settings: Settings) -> Result<()> {
    let health = HealthRegistry::new();
    health.set_component("router", true, "http and websocket routes registered");

    let (bridge, conversations, bridge_detail): (
        Arc<dyn BridgeService>,
        Arc<dyn ConversationService>,
        String,
    ) = match settings.bridge.mode.as_str() {
        "http" => {
            let bridge: Arc<dyn BridgeService> =
                Arc::new(HttpBridge::new(settings.bridge.clone())?);
            bridge.ready().await?;
            let conversations: Arc<dyn ConversationService> =
                Arc::new(HttpConversationService::new(settings.bridge.clone())?);
            (
                bridge,
                conversations,
                format!(
                    "http bridge ready for {}",
                    settings.bridge.base_url.clone().unwrap_or_else(|| "<missing>".to_string())
                ),
            )
        }
        _ => (
            Arc::new(NullBridge),
            Arc::new(InMemoryConversationService::default()),
            "null bridge ready".to_string(),
        ),
    };
    health.set_component("bridge", true, bridge_detail);

    let state = AppState::new(settings.clone(), health, bridge, conversations);
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

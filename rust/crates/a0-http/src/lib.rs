mod error;
mod handlers;
mod models;
mod router;

use std::sync::Arc;

use a0_config::Settings;
use a0_core::{BridgeService, BuildInfo, ConversationService};
use a0_observability::{build_info, HealthRegistry};
use a0_ws::WsHub;

pub use router::build_router;

#[derive(Clone)]
pub struct AppState {
    pub settings: Settings,
    pub build_info: BuildInfo,
    pub health: HealthRegistry,
    pub ws_hub: WsHub,
    pub bridge: Arc<dyn BridgeService>,
    pub conversations: Arc<dyn ConversationService>,
}

impl AppState {
    pub fn new(
        settings: Settings,
        health: HealthRegistry,
        bridge: Arc<dyn BridgeService>,
        conversations: Arc<dyn ConversationService>,
    ) -> Self {
        Self {
            settings,
            build_info: build_info(),
            health,
            ws_hub: WsHub::default(),
            bridge,
            conversations,
        }
    }
}

pub fn test_state() -> AppState {
    let health = HealthRegistry::new();
    health.set_component("bridge", true, "null bridge ready");
    health.set_component("router", true, "http router ready");
    AppState::new(
        a0_config::Settings::default(),
        health,
        handlers::default_bridge(),
        handlers::default_conversations(),
    )
}

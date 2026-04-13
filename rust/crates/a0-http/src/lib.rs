mod error;
mod handlers;
mod models;
mod router;

use std::sync::Arc;
use std::{env, path::PathBuf};

use a0_config::Settings;
use a0_core::{BridgeService, BuildInfo, ConversationService};
use a0_observability::{build_info, HealthRegistry};
use a0_ws::WsHub;

pub use router::build_router;

#[derive(Clone)]
pub struct AppState {
    pub settings: Settings,
    pub build_info: BuildInfo,
    pub runtime_id: String,
    pub ui_asset_root: PathBuf,
    pub workspace_root: PathBuf,
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
            ui_asset_root: resolve_ui_asset_root(&settings),
            workspace_root: PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../.."),
            settings,
            build_info: build_info(),
            runtime_id: uuid::Uuid::new_v4().to_string(),
            health,
            ws_hub: WsHub::default(),
            bridge,
            conversations,
        }
    }
}

fn resolve_ui_asset_root(settings: &Settings) -> PathBuf {
    if let Some(asset_root) = settings.ui.asset_root.as_ref() {
        return PathBuf::from(asset_root);
    }

    if let Ok(current_exe) = env::current_exe() {
        if let Some(prefix_dir) = current_exe.parent().and_then(|dir| dir.parent()) {
            let install_candidate = prefix_dir.join("share/agent-zero/rust/webui");
            if install_candidate.exists() {
                return install_candidate;
            }
        }
    }

    let workspace_candidate =
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../..").join("webui");
    if workspace_candidate.exists() {
        return workspace_candidate;
    }

    PathBuf::from("webui")
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

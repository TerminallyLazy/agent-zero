use serde::Serialize;

use a0_core::{BuildInfo, PluginSummary};
use a0_observability::HealthSnapshot;

#[derive(Debug, Serialize)]
pub struct SuccessEnvelope<T> {
    pub ok: bool,
    pub request_id: String,
    #[serde(flatten)]
    pub data: T,
}

#[derive(Debug, Serialize)]
pub struct VersionResponse {
    pub version: String,
    pub commit: Option<String>,
}

impl From<BuildInfo> for VersionResponse {
    fn from(value: BuildInfo) -> Self {
        Self { version: value.version, commit: value.commit }
    }
}

#[derive(Debug, Serialize)]
pub struct ReadyResponse {
    pub status: &'static str,
    pub ready: bool,
    pub components: Vec<a0_observability::ComponentSnapshot>,
}

impl From<HealthSnapshot> for ReadyResponse {
    fn from(value: HealthSnapshot) -> Self {
        Self { status: value.status, ready: value.ready, components: value.components }
    }
}

#[derive(Debug, Serialize)]
pub struct PluginListResponse {
    pub plugins: Vec<PluginSummary>,
}

#[derive(Debug, Serialize)]
pub struct SettingsResponse {
    pub server_host: String,
    pub server_port: u16,
    pub bridge_mode: String,
}

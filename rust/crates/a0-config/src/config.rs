use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Settings {
    pub server: ServerSettings,
    pub observability: ObservabilitySettings,
    pub bridge: BridgeSettings,
    pub security: SecuritySettings,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            server: ServerSettings { host: "127.0.0.1".to_string(), port: 50001 },
            observability: ObservabilitySettings {
                log_format: "pretty".to_string(),
                log_level: "info".to_string(),
            },
            bridge: BridgeSettings {
                mode: "null".to_string(),
                base_url: None,
                api_key: None,
                timeout_secs: 30,
            },
            security: SecuritySettings {
                auth_mode: "reserved".to_string(),
                csrf_mode: "reserved".to_string(),
                allowed_origins: vec!["http://localhost:50001".to_string()],
            },
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ServerSettings {
    pub host: String,
    pub port: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ObservabilitySettings {
    pub log_format: String,
    pub log_level: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct BridgeSettings {
    pub mode: String,
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub timeout_secs: u64,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SecuritySettings {
    pub auth_mode: String,
    pub csrf_mode: String,
    pub allowed_origins: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct PartialSettings {
    pub server: Option<PartialServerSettings>,
    pub observability: Option<PartialObservabilitySettings>,
    pub bridge: Option<PartialBridgeSettings>,
    pub security: Option<PartialSecuritySettings>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct PartialServerSettings {
    pub host: Option<String>,
    pub port: Option<u16>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct PartialObservabilitySettings {
    pub log_format: Option<String>,
    pub log_level: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct PartialBridgeSettings {
    pub mode: Option<String>,
    pub base_url: Option<String>,
    pub api_key: Option<String>,
    pub timeout_secs: Option<u64>,
}

#[derive(Debug, Clone, Deserialize, Default)]
pub struct PartialSecuritySettings {
    pub auth_mode: Option<String>,
    pub csrf_mode: Option<String>,
    pub allowed_origins: Option<Vec<String>>,
}

impl Settings {
    pub fn apply_partial(&mut self, partial: PartialSettings) {
        if let Some(server) = partial.server {
            if let Some(host) = server.host {
                self.server.host = host;
            }
            if let Some(port) = server.port {
                self.server.port = port;
            }
        }

        if let Some(observability) = partial.observability {
            if let Some(log_format) = observability.log_format {
                self.observability.log_format = log_format;
            }
            if let Some(log_level) = observability.log_level {
                self.observability.log_level = log_level;
            }
        }

        if let Some(bridge) = partial.bridge {
            if let Some(mode) = bridge.mode {
                self.bridge.mode = mode;
            }
            if let Some(base_url) = bridge.base_url {
                self.bridge.base_url = Some(base_url);
            }
            if let Some(api_key) = bridge.api_key {
                self.bridge.api_key = Some(api_key);
            }
            if let Some(timeout_secs) = bridge.timeout_secs {
                self.bridge.timeout_secs = timeout_secs;
            }
        }

        if let Some(security) = partial.security {
            if let Some(auth_mode) = security.auth_mode {
                self.security.auth_mode = auth_mode;
            }
            if let Some(csrf_mode) = security.csrf_mode {
                self.security.csrf_mode = csrf_mode;
            }
            if let Some(allowed_origins) = security.allowed_origins {
                self.security.allowed_origins = allowed_origins;
            }
        }
    }
}

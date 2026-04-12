use std::{env, fs, path::Path};

use anyhow::{Context, Result};

use crate::{Cli, PartialSettings, Settings};

pub fn load_settings(cli: Cli, env_pairs: &[(&str, &str)]) -> Result<Settings> {
    let mut settings = Settings::default();

    if let Some(config_path) = &cli.config {
        let contents = fs::read_to_string(resolve_config_path(config_path))
            .with_context(|| format!("failed to read config file {config_path}"))?;
        let partial: PartialSettings =
            toml::from_str(&contents).with_context(|| "failed to parse config file")?;
        settings.apply_partial(partial);
    }

    apply_env_pairs(&mut settings, env_pairs);
    apply_cli_overrides(&mut settings, &cli);

    Ok(settings)
}

pub fn load_settings_from_env(cli: Cli) -> Result<Settings> {
    let env_pairs: Vec<(String, String)> = env::vars().collect();
    let borrowed: Vec<(&str, &str)> =
        env_pairs.iter().map(|(key, value)| (key.as_str(), value.as_str())).collect();
    load_settings(cli, &borrowed)
}

fn resolve_config_path(path: &str) -> String {
    if Path::new(path).exists() {
        return path.to_string();
    }

    let workspace_relative = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..").join(path);
    workspace_relative.to_string_lossy().to_string()
}

fn apply_env_pairs(settings: &mut Settings, env_pairs: &[(&str, &str)]) {
    for (key, value) in env_pairs {
        match *key {
            "A0_HOST" => settings.server.host = (*value).to_string(),
            "A0_PORT" => {
                if let Ok(port) = value.parse::<u16>() {
                    settings.server.port = port;
                }
            }
            "A0_LOG_FORMAT" => settings.observability.log_format = (*value).to_string(),
            "A0_LOG_LEVEL" => settings.observability.log_level = (*value).to_string(),
            "A0_BRIDGE_MODE" => settings.bridge.mode = (*value).to_string(),
            "A0_BRIDGE_BASE_URL" => settings.bridge.base_url = Some((*value).to_string()),
            "A0_BRIDGE_API_KEY" => settings.bridge.api_key = Some((*value).to_string()),
            "A0_BRIDGE_TIMEOUT_SECS" => {
                if let Ok(timeout_secs) = value.parse::<u64>() {
                    settings.bridge.timeout_secs = timeout_secs;
                }
            }
            "A0_AUTH_MODE" => settings.security.auth_mode = (*value).to_string(),
            "A0_CSRF_MODE" => settings.security.csrf_mode = (*value).to_string(),
            _ => {}
        }
    }
}

fn apply_cli_overrides(settings: &mut Settings, cli: &Cli) {
    if let Some(host) = &cli.host {
        settings.server.host = host.clone();
    }
    if let Some(port) = cli.port {
        settings.server.port = port;
    }
    if let Some(log_format) = &cli.log_format {
        settings.observability.log_format = log_format.clone();
    }
    if let Some(log_level) = &cli.log_level {
        settings.observability.log_level = log_level.clone();
    }
}

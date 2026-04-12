use std::{env, fs, path::Path};

use anyhow::{Context, Result};

use crate::{Cli, PartialSettings, Settings};

pub fn load_settings(cli: Cli, env_pairs: &[(&str, &str)]) -> Result<Settings> {
    let mut settings = Settings::default();

    if let Some(config_path) = discover_config_path(&cli, env_pairs) {
        let contents = fs::read_to_string(resolve_config_path(&config_path))
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

fn discover_config_path(cli: &Cli, env_pairs: &[(&str, &str)]) -> Option<String> {
    cli.config
        .clone()
        .or_else(|| env_value(env_pairs, "A0_CONFIG").map(ToOwned::to_owned))
        .or_else(|| discover_standard_user_config(env_pairs))
}

fn discover_standard_user_config(env_pairs: &[(&str, &str)]) -> Option<String> {
    let xdg_path = env_value(env_pairs, "XDG_CONFIG_HOME")
        .map(|value| Path::new(value).join("agent-zero/rust/agent-zero.toml"));
    if let Some(path) = xdg_path.filter(|path| path.exists()) {
        return Some(path.to_string_lossy().to_string());
    }

    let home_path = env_value(env_pairs, "HOME")
        .map(|value| Path::new(value).join(".config/agent-zero/rust/agent-zero.toml"));
    home_path.filter(|path| path.exists()).map(|path| path.to_string_lossy().to_string())
}

fn env_value<'a>(env_pairs: &'a [(&str, &str)], key: &str) -> Option<&'a str> {
    env_pairs.iter().find_map(|(candidate_key, candidate_value)| {
        (*candidate_key == key).then_some(*candidate_value)
    })
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

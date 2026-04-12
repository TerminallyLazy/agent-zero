use a0_config::{load_settings, Cli, Command};
use std::{
    fs,
    path::{Path, PathBuf},
    time::{SystemTime, UNIX_EPOCH},
};

#[test]
fn cli_values_override_env_and_file() {
    let cli = Cli {
        command: Command::Serve,
        config: Some("rust/config/agent-zero.toml".into()),
        host: Some("127.0.0.1".into()),
        port: Some(60001),
        log_format: Some("json".into()),
        log_level: None,
    };

    let settings = load_settings(
        cli,
        &[("A0_HOST", "0.0.0.0"), ("A0_PORT", "50001"), ("A0_LOG_FORMAT", "pretty")],
    )
    .unwrap();

    assert_eq!(settings.server.host, "127.0.0.1");
    assert_eq!(settings.server.port, 60001);
    assert_eq!(settings.observability.log_format, "json");
}

#[test]
fn bridge_settings_load_from_environment() {
    let cli = Cli {
        command: Command::Serve,
        config: Some("rust/config/agent-zero.toml".into()),
        host: None,
        port: None,
        log_format: None,
        log_level: None,
    };

    let settings = load_settings(
        cli,
        &[
            ("A0_BRIDGE_MODE", "http"),
            ("A0_BRIDGE_BASE_URL", "http://127.0.0.1:50001"),
            ("A0_BRIDGE_API_KEY", "secret"),
            ("A0_BRIDGE_TIMEOUT_SECS", "12"),
        ],
    )
    .unwrap();

    assert_eq!(settings.bridge.mode, "http");
    assert_eq!(settings.bridge.base_url.as_deref(), Some("http://127.0.0.1:50001"));
    assert_eq!(settings.bridge.api_key.as_deref(), Some("secret"));
    assert_eq!(settings.bridge.timeout_secs, 12);
}

#[test]
fn config_path_can_come_from_environment() {
    let config_path = write_test_config("env-config", "10.20.30.40", 61234);
    let cli = Cli {
        command: Command::Serve,
        config: None,
        host: None,
        port: None,
        log_format: None,
        log_level: None,
    };

    let settings = load_settings(cli, &[("A0_CONFIG", config_path.to_str().unwrap())]).unwrap();

    assert_eq!(settings.server.host, "10.20.30.40");
    assert_eq!(settings.server.port, 61234);
}

#[test]
fn settings_load_from_standard_user_config_path() {
    let config_home = unique_temp_dir("config-home");
    let config_path = config_home.join("agent-zero/rust/agent-zero.toml");
    write_config_file(&config_path, "127.0.0.2", 62345);

    let cli = Cli {
        command: Command::Serve,
        config: None,
        host: None,
        port: None,
        log_format: None,
        log_level: None,
    };

    let settings =
        load_settings(cli, &[("XDG_CONFIG_HOME", config_home.to_str().unwrap())]).unwrap();

    assert_eq!(settings.server.host, "127.0.0.2");
    assert_eq!(settings.server.port, 62345);
}

fn write_test_config(label: &str, host: &str, port: u16) -> PathBuf {
    let dir = unique_temp_dir(label);
    let path = dir.join("agent-zero.toml");
    write_config_file(&path, host, port);
    path
}

fn unique_temp_dir(label: &str) -> PathBuf {
    let nanos = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let dir = std::env::temp_dir().join(format!("a0-config-tests-{label}-{nanos}"));
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn write_config_file(path: &Path, host: &str, port: u16) {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).unwrap();
    }
    fs::write(
        path,
        format!(
            r#"[server]
host = "{host}"
port = {port}
"#
        ),
    )
    .unwrap();
}

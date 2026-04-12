use a0_config::{load_settings, Cli, Command};

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

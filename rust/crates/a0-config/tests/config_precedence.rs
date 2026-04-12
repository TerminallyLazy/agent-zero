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

use tracing_subscriber::EnvFilter;

pub fn init_tracing(log_level: &str, log_format: &str) {
    let filter =
        EnvFilter::try_new(log_level.to_string()).unwrap_or_else(|_| EnvFilter::new("info"));
    let builder = tracing_subscriber::fmt().with_env_filter(filter);

    match log_format {
        "json" => builder.json().try_init().ok(),
        _ => builder.try_init().ok(),
    };
}

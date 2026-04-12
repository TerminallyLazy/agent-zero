use anyhow::Result;

use a0_config::{load_settings_from_env, Cli, Command};
use a0_observability::init_tracing;

use crate::bootstrap;

pub async fn run(cli: Cli) -> Result<()> {
    let command = cli.command.clone();
    let settings = load_settings_from_env(cli)?;

    init_tracing(&settings.observability.log_level, &settings.observability.log_format);

    match command {
        Command::Serve => bootstrap::serve(settings).await,
        Command::PrintConfig => {
            println!("{}", serde_json::to_string_pretty(&settings)?);
            Ok(())
        }
        Command::Check => {
            println!("configuration valid");
            Ok(())
        }
    }
}

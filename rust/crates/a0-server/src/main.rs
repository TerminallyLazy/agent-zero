mod bootstrap;
mod commands;

use anyhow::Result;
use clap::Parser;

fn main() -> Result<()> {
    let cli = a0_config::Cli::parse();
    let runtime = tokio::runtime::Runtime::new()?;
    runtime.block_on(commands::run(cli))
}

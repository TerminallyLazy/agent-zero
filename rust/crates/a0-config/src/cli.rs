use clap::{Parser, Subcommand};

#[derive(Debug, Clone, Parser)]
#[command(name = "a0-server", about = "Agent Zero Rust backend skeleton")]
pub struct Cli {
    #[arg(long, env = "A0_CONFIG")]
    pub config: Option<String>,

    #[arg(long)]
    pub host: Option<String>,

    #[arg(long)]
    pub port: Option<u16>,

    #[arg(long)]
    pub log_format: Option<String>,

    #[arg(long)]
    pub log_level: Option<String>,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Clone, Subcommand)]
pub enum Command {
    Serve,
    PrintConfig,
    Check,
}

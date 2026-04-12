use async_trait::async_trait;

use crate::{AppError, BuildInfo, ContextSummary, JobSummary, PluginSummary, ToolSummary};

#[async_trait]
pub trait ContextService: Send + Sync {
    async fn list_contexts(&self) -> Result<Vec<ContextSummary>, AppError>;
}

#[async_trait]
pub trait AgentService: Send + Sync {
    async fn status(&self) -> Result<&'static str, AppError>;
}

#[async_trait]
pub trait PluginService: Send + Sync {
    async fn list_plugins(&self) -> Result<Vec<PluginSummary>, AppError>;
}

#[async_trait]
pub trait JobService: Send + Sync {
    async fn list_jobs(&self) -> Result<Vec<JobSummary>, AppError>;
}

#[async_trait]
pub trait ToolService: Send + Sync {
    async fn list_tools(&self) -> Result<Vec<ToolSummary>, AppError>;
}

#[async_trait]
pub trait BridgeService: Send + Sync {
    async fn mode(&self) -> &'static str;
    async fn ready(&self) -> Result<(), AppError>;
}

pub trait HealthReporter: Send + Sync {
    fn build_info(&self) -> BuildInfo;
}

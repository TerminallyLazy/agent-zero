use async_trait::async_trait;

use crate::{
    AppError, BuildInfo, ContextSummary, ConversationLog, CreateContextRequest,
    CreateContextResponse, JobSummary, PluginSummary, SendMessageRequest, SendMessageResponse,
    StateSnapshot, StateSnapshotRequest, ToolSummary,
};

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

#[async_trait]
pub trait ConversationService: Send + Sync {
    async fn send_external_message(
        &self,
        request: SendMessageRequest,
    ) -> Result<SendMessageResponse, AppError>;
    async fn get_log(&self, context_id: &str, length: usize) -> Result<ConversationLog, AppError>;
    async fn create_context(
        &self,
        request: CreateContextRequest,
    ) -> Result<CreateContextResponse, AppError>;
    async fn build_state_snapshot(
        &self,
        request: StateSnapshotRequest,
    ) -> Result<StateSnapshot, AppError>;
}

pub trait HealthReporter: Send + Sync {
    fn build_info(&self) -> BuildInfo;
}

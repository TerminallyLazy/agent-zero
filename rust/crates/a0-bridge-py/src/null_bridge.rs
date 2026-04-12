use a0_core::{AppError, BridgeService};
use async_trait::async_trait;

#[derive(Debug, Default)]
pub struct NullBridge;

#[async_trait]
impl BridgeService for NullBridge {
    async fn mode(&self) -> &'static str {
        "null"
    }

    async fn ready(&self) -> Result<(), AppError> {
        Ok(())
    }
}

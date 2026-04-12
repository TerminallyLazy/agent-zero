use a0_config::BridgeSettings;
use a0_core::{
    AppError, BridgeService, ConversationLog, ConversationService, SendMessageRequest,
    SendMessageResponse,
};
use async_trait::async_trait;
use reqwest::Client;

#[derive(Debug, Clone)]
pub struct HttpBridge {
    client: Client,
    settings: BridgeSettings,
}

#[derive(Debug, Clone)]
pub struct HttpConversationService {
    client: Client,
    settings: BridgeSettings,
}

impl HttpBridge {
    pub fn new(settings: BridgeSettings) -> Result<Self, AppError> {
        let client = build_client(&settings)?;
        Ok(Self { client, settings })
    }
}

impl HttpConversationService {
    pub fn new(settings: BridgeSettings) -> Result<Self, AppError> {
        let client = build_client(&settings)?;
        Ok(Self { client, settings })
    }
}

#[async_trait]
impl BridgeService for HttpBridge {
    async fn mode(&self) -> &'static str {
        "http"
    }

    async fn ready(&self) -> Result<(), AppError> {
        let base_url = base_url(&self.settings)?;
        let response = apply_api_key(self.client.get(format!("{base_url}/health")), &self.settings)
            .send()
            .await
            .map_err(|error| AppError::Internal(error.to_string()))?;

        if response.status().is_success() {
            Ok(())
        } else {
            Err(AppError::Internal(format!(
                "bridge health check failed with {}",
                response.status()
            )))
        }
    }
}

#[async_trait]
impl ConversationService for HttpConversationService {
    async fn send_external_message(
        &self,
        request: SendMessageRequest,
    ) -> Result<SendMessageResponse, AppError> {
        let base_url = base_url(&self.settings)?;
        let response = apply_api_key(
            self.client
                .post(format!("{base_url}/api_message"))
                .json(&serde_json::json!({
                    "context_id": request.context_id,
                    "message": request.message,
                    "attachments": request.attachment_filenames.iter().map(|filename| serde_json::json!({
                        "filename": filename,
                        "base64": ""
                    })).collect::<Vec<_>>(),
                    "lifetime_hours": request.lifetime_hours,
                    "project_name": request.project_name,
                })),
            &self.settings,
        )
        .send()
        .await
        .map_err(|error| AppError::Internal(error.to_string()))?;

        if response.status().is_success() {
            response
                .json::<SendMessageResponse>()
                .await
                .map_err(|error| AppError::Internal(error.to_string()))
        } else {
            Err(map_remote_error(response.status().as_u16(), response.text().await.ok()))
        }
    }

    async fn get_log(&self, context_id: &str, length: usize) -> Result<ConversationLog, AppError> {
        let base_url = base_url(&self.settings)?;
        let response = apply_api_key(
            self.client
                .get(format!("{base_url}/api_log_get"))
                .query(&[("context_id", context_id), ("length", &length.to_string())]),
            &self.settings,
        )
        .send()
        .await
        .map_err(|error| AppError::Internal(error.to_string()))?;

        if response.status().is_success() {
            let payload = response
                .json::<serde_json::Value>()
                .await
                .map_err(|error| AppError::Internal(error.to_string()))?;
            serde_json::from_value(payload["log"].clone())
                .map_err(|error| AppError::Internal(error.to_string()))
        } else {
            Err(map_remote_error(response.status().as_u16(), response.text().await.ok()))
        }
    }
}

fn build_client(settings: &BridgeSettings) -> Result<Client, AppError> {
    Client::builder()
        .timeout(std::time::Duration::from_secs(settings.timeout_secs))
        .build()
        .map_err(|error| AppError::Internal(error.to_string()))
}

fn base_url(settings: &BridgeSettings) -> Result<&str, AppError> {
    settings.base_url.as_deref().ok_or_else(|| {
        AppError::InvalidRequest("bridge.base_url is required for http mode".to_string())
    })
}

fn apply_api_key(
    builder: reqwest::RequestBuilder,
    settings: &BridgeSettings,
) -> reqwest::RequestBuilder {
    match &settings.api_key {
        Some(api_key) if !api_key.is_empty() => builder.header("X-API-KEY", api_key),
        _ => builder,
    }
}

fn map_remote_error(status: u16, body: Option<String>) -> AppError {
    let message = body.unwrap_or_else(|| format!("remote request failed with status {status}"));
    match status {
        400 => AppError::InvalidRequest(message),
        401 => AppError::Unauthorized,
        403 => AppError::Forbidden,
        404 => AppError::NotFound(message),
        408 => AppError::Timeout(message),
        _ => AppError::Internal(message),
    }
}

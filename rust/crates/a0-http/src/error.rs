use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

use a0_core::AppError;

#[derive(Debug, Serialize)]
pub struct ErrorEnvelope {
    pub ok: bool,
    pub error: ErrorDetail,
    pub request_id: String,
}

#[derive(Debug, Serialize)]
pub struct ErrorDetail {
    pub code: String,
    pub message: String,
}

pub struct HttpError {
    status: StatusCode,
    body: ErrorEnvelope,
}

impl HttpError {
    pub fn new(
        status: StatusCode,
        code: impl Into<String>,
        message: impl Into<String>,
        request_id: String,
    ) -> Self {
        Self {
            status,
            body: ErrorEnvelope {
                ok: false,
                error: ErrorDetail { code: code.into(), message: message.into() },
                request_id,
            },
        }
    }

    pub fn from_app_error(error: AppError, request_id: String) -> Self {
        let status = match error {
            AppError::NotImplemented(_) => StatusCode::NOT_IMPLEMENTED,
            AppError::InvalidRequest(_) => StatusCode::BAD_REQUEST,
            AppError::Unauthorized => StatusCode::UNAUTHORIZED,
            AppError::Forbidden => StatusCode::FORBIDDEN,
            AppError::NotFound(_) => StatusCode::NOT_FOUND,
            AppError::Timeout(_) => StatusCode::REQUEST_TIMEOUT,
            AppError::Internal(_) => StatusCode::INTERNAL_SERVER_ERROR,
        };

        let code = error.code().to_string();
        let message = error.to_string();
        Self::new(status, code, message, request_id)
    }
}

impl IntoResponse for HttpError {
    fn into_response(self) -> Response {
        (self.status, Json(self.body)).into_response()
    }
}

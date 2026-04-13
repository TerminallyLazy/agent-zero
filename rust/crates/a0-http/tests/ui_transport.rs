use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use serde_json::Value;
use tower::ServiceExt;

#[tokio::test]
async fn csrf_token_route_returns_token_and_runtime_id() {
    let app = a0_http::build_router(a0_http::test_state());

    let response = app
        .oneshot(
            Request::builder().method("GET").uri("/api/csrf_token").body(Body::empty()).unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["ok"].as_bool(), Some(true));
    assert!(json["token"].as_str().is_some_and(|value| !value.is_empty()));
    assert!(json["runtime_id"].as_str().is_some_and(|value| !value.is_empty()));
}

#[tokio::test]
async fn message_async_json_returns_ack_and_creates_context() {
    let app = a0_http::build_router(a0_http::test_state());

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/message_async")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"text":"hello from ui","context":null,"message_id":"m-1"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    let context_id = json["context"].as_str().unwrap().to_string();

    assert_eq!(json["message"].as_str(), Some("Message received."));

    let log_response = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri(format!("/api_log_get?context_id={context_id}&length=10"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(log_response.status(), StatusCode::OK);
    let log_body = axum::body::to_bytes(log_response.into_body(), usize::MAX).await.unwrap();
    let log_json: Value = serde_json::from_slice(&log_body).unwrap();

    assert_eq!(log_json["log"]["items"].as_array().unwrap().len(), 2);
    assert_eq!(log_json["log"]["items"][0]["content"].as_str(), Some("hello from ui"));
}

#[tokio::test]
async fn message_route_returns_synchronous_response() {
    let app = a0_http::build_router(a0_http::test_state());

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"text":"sync hello","context":null}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["message"].as_str(), Some("Rust skeleton received: sync hello"));
    assert!(json["context"].as_str().is_some());
}

#[tokio::test]
async fn message_async_accepts_multipart_attachments() {
    let app = a0_http::build_router(a0_http::test_state());
    let boundary = "x-a0-boundary";
    let body = format!(
        concat!(
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"text\"\r\n\r\n",
            "hello with file\r\n",
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"context\"\r\n\r\n",
            "\r\n",
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"message_id\"\r\n\r\n",
            "m-2\r\n",
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"attachments\"; filename=\"notes.txt\"\r\n",
            "Content-Type: text/plain\r\n\r\n",
            "file body\r\n",
            "--{boundary}--\r\n"
        ),
        boundary = boundary
    );

    let response = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/message_async")
                .header("content-type", format!("multipart/form-data; boundary={boundary}"))
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let response_body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let response_json: Value = serde_json::from_slice(&response_body).unwrap();
    let context_id = response_json["context"].as_str().unwrap().to_string();

    let log_response = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri(format!("/api_log_get?context_id={context_id}&length=10"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    let log_body = axum::body::to_bytes(log_response.into_body(), usize::MAX).await.unwrap();
    let log_json: Value = serde_json::from_slice(&log_body).unwrap();

    assert_eq!(
        log_json["log"]["items"][0]["attachments"].as_array().unwrap()[0].as_str(),
        Some("notes.txt")
    );
    assert_eq!(
        log_json["log"]["items"][1]["content"].as_str(),
        Some("Rust skeleton received: hello with file (1 attachment)")
    );
}

#[tokio::test]
async fn message_async_accepts_attachment_only_payloads() {
    let app = a0_http::build_router(a0_http::test_state());
    let boundary = "x-a0-boundary";
    let body = format!(
        concat!(
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"text\"\r\n\r\n",
            "\r\n",
            "--{boundary}\r\n",
            "Content-Disposition: form-data; name=\"attachments\"; filename=\"only.txt\"\r\n",
            "Content-Type: text/plain\r\n\r\n",
            "file body\r\n",
            "--{boundary}--\r\n"
        ),
        boundary = boundary
    );

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/message_async")
                .header("content-type", format!("multipart/form-data; boundary={boundary}"))
                .body(Body::from(body))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
}

use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use serde_json::Value;
use tower::ServiceExt;

#[tokio::test]
async fn api_message_creates_context_and_returns_response() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"Hello from test","lifetime_hours":24}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);

    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["context_id"].as_str().is_some(), true);
    assert!(json["response"].as_str().unwrap().contains("Hello from test"));
}

#[tokio::test]
async fn api_message_continues_context_and_api_log_get_returns_recent_items() {
    let app = a0_http::build_router(a0_http::test_state());

    let first = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"first"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let first_body = axum::body::to_bytes(first.into_body(), usize::MAX).await.unwrap();
    let first_json: Value = serde_json::from_slice(&first_body).unwrap();
    let context_id = first_json["context_id"].as_str().unwrap().to_string();

    let second = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(format!(r#"{{"context_id":"{context_id}","message":"second"}}"#)))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(second.status(), StatusCode::OK);

    let log = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri(format!("/api_log_get?context_id={context_id}&length=10"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(log.status(), StatusCode::OK);

    let log_body = axum::body::to_bytes(log.into_body(), usize::MAX).await.unwrap();
    let log_json: Value = serde_json::from_slice(&log_body).unwrap();

    assert_eq!(log_json["context_id"].as_str(), Some(context_id.as_str()));
    assert_eq!(log_json["log"]["returned_items"].as_u64(), Some(4));
    assert_eq!(log_json["log"]["items"][0]["role"].as_str(), Some("user"));
    assert_eq!(log_json["log"]["items"][3]["role"].as_str(), Some("assistant"));
}

#[tokio::test]
async fn api_message_rejects_project_change_on_existing_context() {
    let app = a0_http::build_router(a0_http::test_state());

    let first = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"first","project_name":"alpha"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let first_body = axum::body::to_bytes(first.into_body(), usize::MAX).await.unwrap();
    let first_json: Value = serde_json::from_slice(&first_body).unwrap();
    let context_id = first_json["context_id"].as_str().unwrap().to_string();

    let second = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(format!(
                    r#"{{"context_id":"{context_id}","message":"second","project_name":"beta"}}"#
                )))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(second.status(), StatusCode::BAD_REQUEST);
}

#[tokio::test]
async fn api_log_get_accepts_post_json_body() {
    let app = a0_http::build_router(a0_http::test_state());

    let first = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"body-log"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let first_body = axum::body::to_bytes(first.into_body(), usize::MAX).await.unwrap();
    let first_json: Value = serde_json::from_slice(&first_body).unwrap();
    let context_id = first_json["context_id"].as_str().unwrap().to_string();

    let log = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_log_get")
                .header("content-type", "application/json")
                .body(Body::from(format!(r#"{{"context_id":"{context_id}","length":2}}"#)))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(log.status(), StatusCode::OK);

    let log_body = axum::body::to_bytes(log.into_body(), usize::MAX).await.unwrap();
    let log_json: Value = serde_json::from_slice(&log_body).unwrap();
    assert_eq!(log_json["log"]["returned_items"].as_u64(), Some(2));
}

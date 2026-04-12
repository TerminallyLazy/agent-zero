use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use serde_json::Value;
use tower::ServiceExt;

#[tokio::test]
async fn chat_create_returns_new_context_id() {
    let app = a0_http::build_router(a0_http::test_state());

    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/chat_create")
                .header("content-type", "application/json")
                .body(Body::from(r#"{}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    assert_eq!(json["ok"].as_bool(), Some(true));
    assert!(json["ctxid"].as_str().is_some());
}

#[tokio::test]
async fn poll_returns_contexts_and_logs_for_selected_context() {
    let app = a0_http::build_router(a0_http::test_state());

    let first = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"poll seed"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let first_body = axum::body::to_bytes(first.into_body(), usize::MAX).await.unwrap();
    let first_json: Value = serde_json::from_slice(&first_body).unwrap();
    let context_id = first_json["context_id"].as_str().unwrap().to_string();

    let poll = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/poll")
                .header("content-type", "application/json")
                .body(Body::from(format!(
                    r#"{{"context":"{context_id}","log_from":0,"notifications_from":0,"timezone":"UTC"}}"#
                )))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(poll.status(), StatusCode::OK);
    let poll_body = axum::body::to_bytes(poll.into_body(), usize::MAX).await.unwrap();
    let poll_json: Value = serde_json::from_slice(&poll_body).unwrap();

    assert_eq!(poll_json["context"].as_str(), Some(context_id.as_str()));
    assert_eq!(poll_json["contexts"].as_array().unwrap().len(), 1);
    assert_eq!(poll_json["logs"].as_array().unwrap().len(), 2);
    assert_eq!(poll_json["notifications"].as_array().unwrap().len(), 0);
    assert_eq!(poll_json["tasks"].as_array().unwrap().len(), 0);
}

#[tokio::test]
async fn poll_accepts_minimal_body_with_defaults() {
    let app = a0_http::build_router(a0_http::test_state());

    let seeded = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"poll seed"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let seeded_body = axum::body::to_bytes(seeded.into_body(), usize::MAX).await.unwrap();
    let seeded_json: Value = serde_json::from_slice(&seeded_body).unwrap();
    let context_id = seeded_json["context_id"].as_str().unwrap().to_string();

    let poll = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/poll")
                .header("content-type", "application/json")
                .body(Body::from(format!(r#"{{"context":"{context_id}"}}"#)))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(poll.status(), StatusCode::OK);
    let poll_body = axum::body::to_bytes(poll.into_body(), usize::MAX).await.unwrap();
    let poll_json: Value = serde_json::from_slice(&poll_body).unwrap();

    assert_eq!(poll_json["context"].as_str(), Some(context_id.as_str()));
    assert_eq!(poll_json["logs"].as_array().unwrap().len(), 2);
}

#[tokio::test]
async fn chat_create_inherits_project_from_current_context() {
    let app = a0_http::build_router(a0_http::test_state());

    let first = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api_message")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"message":"seed","project_name":"alpha"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    let first_body = axum::body::to_bytes(first.into_body(), usize::MAX).await.unwrap();
    let first_json: Value = serde_json::from_slice(&first_body).unwrap();
    let current_context = first_json["context_id"].as_str().unwrap();

    let created = app
        .clone()
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/chat_create")
                .header("content-type", "application/json")
                .body(Body::from(format!(r#"{{"current_context":"{current_context}"}}"#)))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(created.status(), StatusCode::OK);
    let created_body = axum::body::to_bytes(created.into_body(), usize::MAX).await.unwrap();
    let created_json: Value = serde_json::from_slice(&created_body).unwrap();
    let new_context = created_json["ctxid"].as_str().unwrap().to_string();

    let poll = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/poll")
                .header("content-type", "application/json")
                .body(Body::from(format!(
                    r#"{{"context":"{new_context}","log_from":0,"notifications_from":0,"timezone":"UTC"}}"#
                )))
                .unwrap(),
        )
        .await
        .unwrap();

    let poll_body = axum::body::to_bytes(poll.into_body(), usize::MAX).await.unwrap();
    let poll_json: Value = serde_json::from_slice(&poll_body).unwrap();
    assert_eq!(poll_json["contexts"][0]["project"].as_str(), Some("alpha"));
}

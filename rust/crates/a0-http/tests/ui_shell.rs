use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use tower::ServiceExt;

#[tokio::test]
async fn index_route_serves_agent_zero_html_shell() {
    let app = a0_http::build_router(a0_http::test_state());
    let response =
        app.oneshot(Request::builder().uri("/").body(Body::empty()).unwrap()).await.unwrap();

    assert_eq!(response.status(), StatusCode::OK);

    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let html = String::from_utf8(body.to_vec()).unwrap();

    assert!(html.contains("<title>Agent Zero</title>"));
    assert!(html.contains("globalThis.runtimeInfo"));
    assert!(!html.contains("{{runtime_id}}"));
    assert!(!html.contains("{{version_no}}"));
}

#[tokio::test]
async fn static_assets_are_served_from_webui_root() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(Request::builder().uri("/index.css").body(Body::empty()).unwrap())
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response.headers().get("content-type").and_then(|value| value.to_str().ok()),
        Some("text/css")
    );
}

use tower::ServiceExt;

#[tokio::test]
async fn health_route_returns_ok_true() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            axum::http::Request::builder().uri("/health").body(axum::body::Body::empty()).unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), axum::http::StatusCode::OK);
}

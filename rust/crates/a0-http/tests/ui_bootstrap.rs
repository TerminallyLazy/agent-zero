use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use serde_json::Value;
use tower::ServiceExt;

#[tokio::test]
async fn load_webui_extensions_returns_matching_entries() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/load_webui_extensions")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"extension_point":"initFw_end","filters":["*.js","*.mjs"]}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();
    let extensions = json["extensions"].as_array().unwrap();

    assert!(extensions.iter().any(|entry| {
        entry.as_str() == Some("extensions/webui/initFw_end/selfUpdateGlobal.js")
    }));
}

#[tokio::test]
async fn settings_get_returns_settings_and_additional_metadata() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/settings_get")
                .header("content-type", "application/json")
                .body(Body::from("{}"))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert!(json["settings"].is_object());
    assert!(json["additional"].is_object());
    assert!(json["settings"]["stt_model_size"].is_string());
    assert!(json["additional"]["agent_subdirs"].is_array());
}

#[tokio::test]
async fn projects_list_options_returns_real_project_entries() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/projects")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"action":"list_options"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["ok"].as_bool(), Some(true));
    assert!(json["data"]
        .as_array()
        .unwrap()
        .iter()
        .any(|entry| { entry["key"].as_str() == Some("ce-testing") }));
}

#[tokio::test]
async fn agents_list_returns_real_agent_profiles() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("POST")
                .uri("/api/agents")
                .header("content-type", "application/json")
                .body(Body::from(r#"{"action":"list"}"#))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let json: Value = serde_json::from_slice(&body).unwrap();

    assert_eq!(json["ok"].as_bool(), Some(true));
    assert!(json["data"]
        .as_array()
        .unwrap()
        .iter()
        .any(|entry| { entry["key"].as_str() == Some("developer") }));
}

#[tokio::test]
async fn plugin_extension_assets_are_served() {
    let app = a0_http::build_router(a0_http::test_state());
    let response = app
        .oneshot(
            Request::builder()
                .method("GET")
                .uri("/plugins/_skills/extensions/webui/initFw_end/skills-menu-injector.js")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = axum::body::to_bytes(response.into_body(), usize::MAX).await.unwrap();
    let text = String::from_utf8(body.to_vec()).unwrap();
    assert!(text.contains("skills"));
}

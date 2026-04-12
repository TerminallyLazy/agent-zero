use std::time::Duration;

use futures_util::{SinkExt, StreamExt};
use tokio_tungstenite::{connect_async, tungstenite::Message};

#[tokio::test]
async fn websocket_ping_round_trip_returns_pong() {
    let app = a0_http::build_router(a0_http::test_state());
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();

    let server = tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });

    tokio::time::sleep(Duration::from_millis(50)).await;

    let url = format!("ws://{}/ws", addr);
    let (mut socket, _) = connect_async(url).await.unwrap();

    let hello = socket.next().await.unwrap().unwrap();
    let hello_text = hello.into_text().unwrap();
    assert!(hello_text.contains("\"event\":\"hello\""));

    socket
        .send(Message::Text(
            r#"{"event":"ping","correlationId":"00000000-0000-0000-0000-000000000001","data":{"source":"test"}}"#
                .to_string()
                .into(),
        ))
        .await
        .unwrap();

    let reply = socket.next().await.unwrap().unwrap();
    let reply_text = reply.into_text().unwrap();
    assert!(reply_text.contains("\"event\":\"ping\""));
    assert!(reply_text.contains("\"message\":\"pong\""));

    server.abort();
}

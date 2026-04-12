use a0_ws::messages::ServerEnvelope;

#[test]
fn ping_envelope_contains_required_metadata() {
    let envelope =
        ServerEnvelope::new("ping", "rust.stub.health", serde_json::json!({"ok": true}), None);
    assert_eq!(envelope.event, "ping");
    assert_eq!(envelope.handler_id, "rust.stub.health");
    assert!(!envelope.event_id.is_nil());
}

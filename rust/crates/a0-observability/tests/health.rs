use a0_observability::HealthRegistry;

#[test]
fn readiness_turns_false_when_any_component_is_unready() {
    let registry = HealthRegistry::new();
    registry.set_component("bridge", false, "null bridge offline");
    assert!(!registry.ready().ready);
}

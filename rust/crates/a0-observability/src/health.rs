use std::{
    collections::BTreeMap,
    sync::{Arc, RwLock},
};

use serde::Serialize;

#[derive(Debug, Clone, Default)]
pub struct HealthRegistry {
    inner: Arc<RwLock<BTreeMap<String, ComponentHealth>>>,
}

#[derive(Debug, Clone)]
pub struct ComponentHealth {
    pub ready: bool,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct ComponentSnapshot {
    pub name: String,
    pub ready: bool,
    pub detail: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct HealthSnapshot {
    pub ok: bool,
    pub status: &'static str,
    pub ready: bool,
    pub components: Vec<ComponentSnapshot>,
}

impl HealthRegistry {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn set_component(&self, name: &str, ready: bool, detail: impl Into<String>) {
        self.inner
            .write()
            .expect("health lock poisoned")
            .insert(name.to_string(), ComponentHealth { ready, detail: detail.into() });
    }

    pub fn live(&self) -> HealthSnapshot {
        HealthSnapshot { ok: true, status: "live", ready: true, components: self.components() }
    }

    pub fn ready(&self) -> HealthSnapshot {
        let components = self.components();
        let ready = components.iter().all(|component| component.ready);
        HealthSnapshot {
            ok: ready,
            status: if ready { "ready" } else { "degraded" },
            ready,
            components,
        }
    }

    fn components(&self) -> Vec<ComponentSnapshot> {
        self.inner
            .read()
            .expect("health lock poisoned")
            .iter()
            .map(|(name, health)| ComponentSnapshot {
                name: name.clone(),
                ready: health.ready,
                detail: health.detail.clone(),
            })
            .collect()
    }
}

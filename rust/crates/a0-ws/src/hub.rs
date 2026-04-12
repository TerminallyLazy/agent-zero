use std::{collections::HashMap, sync::Arc};

use tokio::sync::{mpsc, RwLock};

use crate::messages::ServerEnvelope;

#[derive(Clone, Default)]
pub struct WsHub {
    clients: Arc<RwLock<HashMap<String, mpsc::UnboundedSender<String>>>>,
}

impl WsHub {
    pub async fn register(&self, connection_id: String, sender: mpsc::UnboundedSender<String>) {
        self.clients.write().await.insert(connection_id, sender);
    }

    pub async fn unregister(&self, connection_id: &str) {
        self.clients.write().await.remove(connection_id);
    }

    pub async fn broadcast_json(&self, envelope: &ServerEnvelope) {
        let json = match serde_json::to_string(envelope) {
            Ok(json) => json,
            Err(_) => return,
        };

        for sender in self.clients.read().await.values() {
            let _ = sender.send(json.clone());
        }
    }
}

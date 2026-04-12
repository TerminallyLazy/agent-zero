# Rust Backend Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable Rust backend skeleton for Agent Zero with typed config, HTTP/WebSocket stubs, health/readiness, observability, and migration seams for later Python replacement.

**Architecture:** The implementation uses a Rust workspace with a single `axum` server binary and small focused crates for config, HTTP, WebSocket, observability, core traits, and a null Python bridge. The first milestone preserves only the high-value backend contracts and intentionally returns typed stub responses for unsupported behavior.

**Tech Stack:** Rust, tokio, axum, clap, serde, tracing, uuid, tower-http, tokio-tungstenite or axum WebSocket support, cargo test

---

## File Structure

### New files and responsibilities

- `rust/Cargo.toml`: workspace definition and shared dependencies
- `rust/rustfmt.toml`: formatting rules
- `rust/crates/a0-server/Cargo.toml`: server binary dependencies
- `rust/crates/a0-server/src/main.rs`: CLI entrypoint and top-level error handling
- `rust/crates/a0-server/src/commands.rs`: `serve`, `print-config`, and `check` command dispatch
- `rust/crates/a0-server/src/bootstrap.rs`: server wiring and graceful shutdown
- `rust/crates/a0-server/src/state.rs`: `AppState` construction
- `rust/crates/a0-http/Cargo.toml`: HTTP crate dependencies
- `rust/crates/a0-http/src/lib.rs`: router exports
- `rust/crates/a0-http/src/router.rs`: HTTP route registration
- `rust/crates/a0-http/src/handlers.rs`: route handlers
- `rust/crates/a0-http/src/error.rs`: HTTP error envelope and mapping
- `rust/crates/a0-http/src/models.rs`: HTTP DTOs
- `rust/crates/a0-http/src/middleware.rs`: request ID and tracing middleware helpers
- `rust/crates/a0-ws/Cargo.toml`: WebSocket crate dependencies
- `rust/crates/a0-ws/src/lib.rs`: WS exports
- `rust/crates/a0-ws/src/hub.rs`: connection manager and broadcast/request primitives
- `rust/crates/a0-ws/src/messages.rs`: event envelope types
- `rust/crates/a0-ws/src/handlers.rs`: `hello`, `ping`, and stub event handlers
- `rust/crates/a0-core/Cargo.toml`: core crate dependencies
- `rust/crates/a0-core/src/lib.rs`: exports
- `rust/crates/a0-core/src/errors.rs`: domain errors
- `rust/crates/a0-core/src/services.rs`: core service traits
- `rust/crates/a0-core/src/types.rs`: shared domain types
- `rust/crates/a0-config/Cargo.toml`: config crate dependencies
- `rust/crates/a0-config/src/lib.rs`: config exports
- `rust/crates/a0-config/src/cli.rs`: `clap` models
- `rust/crates/a0-config/src/config.rs`: typed config structs
- `rust/crates/a0-config/src/load.rs`: layered config loading
- `rust/crates/a0-observability/Cargo.toml`: observability dependencies
- `rust/crates/a0-observability/src/lib.rs`: observability exports
- `rust/crates/a0-observability/src/tracing.rs`: tracing bootstrap
- `rust/crates/a0-observability/src/health.rs`: health registry
- `rust/crates/a0-observability/src/build.rs`: build metadata helpers
- `rust/crates/a0-bridge-py/Cargo.toml`: bridge crate dependencies
- `rust/crates/a0-bridge-py/src/lib.rs`: bridge exports
- `rust/crates/a0-bridge-py/src/null_bridge.rs`: no-op bridge
- `rust/config/agent-zero.toml`: sample config file
- `rust/tests/http_smoke.rs`: HTTP integration tests
- `rust/tests/ws_smoke.rs`: WS integration tests
- `rust/tests/config_precedence.rs`: config tests
- `docs/developer/rust-backend-skeleton.md`: migration-focused developer doc

### Existing files to modify

- `README.md`: add Rust backend skeleton developer instructions

## Task 1: Create The Rust Workspace

**Files:**
- Create: `rust/Cargo.toml`
- Create: `rust/rustfmt.toml`
- Create: `rust/crates/a0-server/Cargo.toml`
- Create: `rust/crates/a0-http/Cargo.toml`
- Create: `rust/crates/a0-ws/Cargo.toml`
- Create: `rust/crates/a0-core/Cargo.toml`
- Create: `rust/crates/a0-config/Cargo.toml`
- Create: `rust/crates/a0-observability/Cargo.toml`
- Create: `rust/crates/a0-bridge-py/Cargo.toml`

- [ ] **Step 1: Write the failing workspace boot test**

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo metadata --format-version 1
```

Expected: FAIL because the Rust workspace does not exist yet.

- [ ] **Step 2: Create the workspace manifest**

```toml
[workspace]
members = [
    "crates/a0-server",
    "crates/a0-http",
    "crates/a0-ws",
    "crates/a0-core",
    "crates/a0-config",
    "crates/a0-observability",
    "crates/a0-bridge-py",
]
resolver = "2"

[workspace.package]
edition = "2021"
license = "MIT"
version = "0.1.0"

[workspace.dependencies]
anyhow = "1"
async-trait = "0.1"
axum = { version = "0.8", features = ["macros", "ws"] }
clap = { version = "4.5", features = ["derive", "env"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["macros", "rt-multi-thread", "signal", "sync", "time", "net"] }
tower = "0.5"
tower-http = { version = "0.6", features = ["cors", "trace", "request-id"] }
tracing = "0.1"
tracing-subscriber = { version = "0.3", features = ["env-filter", "fmt", "json"] }
uuid = { version = "1", features = ["serde", "v4"] }
chrono = { version = "0.4", features = ["serde", "clock"] }
thiserror = "2"
toml = "0.8"
```

- [ ] **Step 3: Add per-crate `Cargo.toml` manifests**

```toml
[package]
name = "a0-server"
version.workspace = true
edition.workspace = true
license.workspace = true

[dependencies]
anyhow.workspace = true
a0-bridge-py = { path = "../a0-bridge-py" }
a0-config = { path = "../a0-config" }
a0-core = { path = "../a0-core" }
a0-http = { path = "../a0-http" }
a0-observability = { path = "../a0-observability" }
a0-ws = { path = "../a0-ws" }
tokio.workspace = true
tracing.workspace = true
```

Repeat the same pattern for the other crate manifests, only listing the dependencies each crate actually needs.

- [ ] **Step 4: Add workspace formatting rules**

```toml
max_width = 100
use_small_heuristics = "Max"
```

- [ ] **Step 5: Run workspace metadata again**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo metadata --format-version 1 >/tmp/agent-zero-rust-metadata.json && echo OK
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/Cargo.toml /Users/lazy/Documents/agent-zero/rust/rustfmt.toml /Users/lazy/Documents/agent-zero/rust/crates/*/Cargo.toml
git commit -m "build: add rust workspace skeleton"
```

## Task 2: Add Typed Config And CLI

**Files:**
- Create: `rust/crates/a0-config/src/lib.rs`
- Create: `rust/crates/a0-config/src/cli.rs`
- Create: `rust/crates/a0-config/src/config.rs`
- Create: `rust/crates/a0-config/src/load.rs`
- Create: `rust/config/agent-zero.toml`
- Test: `rust/tests/config_precedence.rs`

- [ ] **Step 1: Write the failing config precedence test**

```rust
use a0_config::{load_settings, Cli, Command};

#[test]
fn cli_values_override_env_and_file() {
    let cli = Cli {
        command: Command::Serve,
        config: Some("rust/config/agent-zero.toml".into()),
        host: Some("127.0.0.1".into()),
        port: Some(60001),
        log_format: Some("json".into()),
    };

    let settings = load_settings(cli, &[
        ("A0_HOST", "0.0.0.0"),
        ("A0_PORT", "50001"),
        ("A0_LOG_FORMAT", "pretty"),
    ]).unwrap();

    assert_eq!(settings.server.host, "127.0.0.1");
    assert_eq!(settings.server.port, 60001);
    assert_eq!(settings.observability.log_format, "json");
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test config_precedence cli_values_override_env_and_file -- --exact
```

Expected: FAIL because `a0_config` exports and the test do not exist yet.

- [ ] **Step 3: Implement CLI models**

```rust
use clap::{Parser, Subcommand};

#[derive(Debug, Clone, Parser)]
#[command(name = "a0-server", about = "Agent Zero Rust backend skeleton")]
pub struct Cli {
    #[arg(long)]
    pub config: Option<String>,

    #[arg(long)]
    pub host: Option<String>,

    #[arg(long)]
    pub port: Option<u16>,

    #[arg(long)]
    pub log_format: Option<String>,

    #[command(subcommand)]
    pub command: Command,
}

#[derive(Debug, Clone, Subcommand)]
pub enum Command {
    Serve,
    PrintConfig,
    Check,
}
```

- [ ] **Step 4: Implement typed settings and layered loading**

```rust
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct Settings {
    pub server: ServerSettings,
    pub observability: ObservabilitySettings,
    pub bridge: BridgeSettings,
    pub security: SecuritySettings,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ServerSettings {
    pub host: String,
    pub port: u16,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct ObservabilitySettings {
    pub log_format: String,
    pub log_level: String,
}
```

Load defaults first, merge file config, then env pairs, then CLI fields.

- [ ] **Step 5: Add sample config file**

```toml
[server]
host = "127.0.0.1"
port = 50001

[observability]
log_format = "pretty"
log_level = "info"

[bridge]
mode = "null"

[security]
auth_mode = "reserved"
csrf_mode = "reserved"
allowed_origins = ["http://localhost:50001"]
```

- [ ] **Step 6: Run config test to verify it passes**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test config_precedence cli_values_override_env_and_file -- --exact
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-config/src /Users/lazy/Documents/agent-zero/rust/config/agent-zero.toml /Users/lazy/Documents/agent-zero/rust/tests/config_precedence.rs
git commit -m "feat: add rust config and cli loading"
```

## Task 3: Add Core Traits And Shared Types

**Files:**
- Create: `rust/crates/a0-core/src/lib.rs`
- Create: `rust/crates/a0-core/src/errors.rs`
- Create: `rust/crates/a0-core/src/services.rs`
- Create: `rust/crates/a0-core/src/types.rs`

- [ ] **Step 1: Write the failing core compile check**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo check -p a0-core
```

Expected: FAIL because the core crate source files do not exist yet.

- [ ] **Step 2: Add shared domain error types**

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("not implemented: {0}")]
    NotImplemented(&'static str),
    #[error("invalid request: {0}")]
    InvalidRequest(String),
    #[error("unauthorized")]
    Unauthorized,
    #[error("forbidden")]
    Forbidden,
    #[error("not found: {0}")]
    NotFound(String),
    #[error("timeout: {0}")]
    Timeout(String),
    #[error("internal: {0}")]
    Internal(String),
}
```

- [ ] **Step 3: Add shared types and service traits**

```rust
use async_trait::async_trait;

#[derive(Debug, Clone)]
pub struct ContextSummary {
    pub id: String,
    pub name: String,
}

#[async_trait]
pub trait ContextService: Send + Sync {
    async fn list_contexts(&self) -> Result<Vec<ContextSummary>, AppError>;
}

#[async_trait]
pub trait BridgeService: Send + Sync {
    async fn mode(&self) -> &'static str;
}
```

Add the same pattern for `AgentService`, `PluginService`, `JobService`, `ToolService`, and `HealthReporter`.

- [ ] **Step 4: Export a stable public surface**

```rust
pub mod errors;
pub mod services;
pub mod types;

pub use errors::AppError;
pub use services::*;
pub use types::*;
```

- [ ] **Step 5: Run `cargo check` to verify it passes**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo check -p a0-core
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-core/src
git commit -m "feat: add rust core service traits"
```

## Task 4: Add Observability And Health Registry

**Files:**
- Create: `rust/crates/a0-observability/src/lib.rs`
- Create: `rust/crates/a0-observability/src/tracing.rs`
- Create: `rust/crates/a0-observability/src/health.rs`
- Create: `rust/crates/a0-observability/src/build.rs`

- [ ] **Step 1: Write the failing health registry test**

```rust
use a0_observability::HealthRegistry;

#[test]
fn readiness_turns_false_when_any_component_is_unready() {
    let registry = HealthRegistry::new();
    registry.set_component("bridge", false, "null bridge offline");
    assert!(!registry.ready().ready);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test -p a0-observability readiness_turns_false_when_any_component_is_unready -- --exact
```

Expected: FAIL because the registry does not exist yet.

- [ ] **Step 3: Implement the health registry**

```rust
use std::collections::BTreeMap;
use std::sync::{Arc, RwLock};

#[derive(Debug, Clone)]
pub struct HealthRegistry {
    inner: Arc<RwLock<BTreeMap<String, ComponentHealth>>>,
}

#[derive(Debug, Clone)]
pub struct ComponentHealth {
    pub ready: bool,
    pub detail: String,
}
```

Expose `set_component`, `live`, and `ready` methods that build response snapshots.

- [ ] **Step 4: Implement tracing bootstrap**

```rust
pub fn init_tracing(log_level: &str, log_format: &str) {
    let filter = tracing_subscriber::EnvFilter::try_new(log_level.to_string())
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));

    match log_format {
        "json" => tracing_subscriber::fmt().with_env_filter(filter).json().init(),
        _ => tracing_subscriber::fmt().with_env_filter(filter).init(),
    }
}
```

- [ ] **Step 5: Run the observability test**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test -p a0-observability readiness_turns_false_when_any_component_is_unready -- --exact
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-observability/src
git commit -m "feat: add rust observability primitives"
```

## Task 5: Add Null Python Bridge

**Files:**
- Create: `rust/crates/a0-bridge-py/src/lib.rs`
- Create: `rust/crates/a0-bridge-py/src/null_bridge.rs`

- [ ] **Step 1: Write the failing bridge compile check**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo check -p a0-bridge-py
```

Expected: FAIL because the bridge source files do not exist yet.

- [ ] **Step 2: Implement the null bridge**

```rust
use a0_core::BridgeService;
use async_trait::async_trait;

#[derive(Debug, Default)]
pub struct NullBridge;

#[async_trait]
impl BridgeService for NullBridge {
    async fn mode(&self) -> &'static str {
        "null"
    }
}
```

- [ ] **Step 3: Export a constructor**

```rust
pub mod null_bridge;

pub use null_bridge::NullBridge;
```

- [ ] **Step 4: Run `cargo check`**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo check -p a0-bridge-py
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-bridge-py/src
git commit -m "feat: add null python bridge"
```

## Task 6: Add WebSocket Messages And Hub

**Files:**
- Create: `rust/crates/a0-ws/src/lib.rs`
- Create: `rust/crates/a0-ws/src/messages.rs`
- Create: `rust/crates/a0-ws/src/hub.rs`
- Create: `rust/crates/a0-ws/src/handlers.rs`
- Test: `rust/tests/ws_smoke.rs`

- [ ] **Step 1: Write the failing WebSocket envelope test**

```rust
use a0_ws::messages::ServerEnvelope;

#[test]
fn ping_envelope_contains_required_metadata() {
    let envelope = ServerEnvelope::new("ping", "rust.stub.health", serde_json::json!({"ok": true}), None);
    assert_eq!(envelope.event, "ping");
    assert_eq!(envelope.handler_id, "rust.stub.health");
    assert!(envelope.event_id.to_string().len() > 10);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test ws_smoke ping_envelope_contains_required_metadata -- --exact
```

Expected: FAIL because the WebSocket crate sources do not exist yet.

- [ ] **Step 3: Implement message envelope types**

```rust
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ServerEnvelope {
    pub event: String,
    #[serde(rename = "eventId")]
    pub event_id: Uuid,
    #[serde(rename = "correlationId")]
    pub correlation_id: Option<Uuid>,
    #[serde(rename = "handlerId")]
    pub handler_id: String,
    pub ts: DateTime<Utc>,
    pub data: serde_json::Value,
}
```

- [ ] **Step 4: Implement a simple in-memory hub**

```rust
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::{mpsc, RwLock};

#[derive(Clone, Default)]
pub struct WsHub {
    clients: Arc<RwLock<HashMap<String, mpsc::UnboundedSender<String>>>>,
}
```

Expose `register`, `unregister`, and `broadcast_json` methods.

- [ ] **Step 5: Implement `hello`, `ping`, and `not_implemented` event handling**

```rust
pub fn handle_event(event: &str) -> (&'static str, serde_json::Value) {
    match event {
        "hello" => ("hello", serde_json::json!({"ok": true, "message": "hello"})),
        "ping" => ("ping", serde_json::json!({"ok": true, "message": "pong"})),
        _ => ("not_implemented", serde_json::json!({"ok": false, "code": "not_implemented"})),
    }
}
```

- [ ] **Step 6: Run the WebSocket test**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test ws_smoke ping_envelope_contains_required_metadata -- --exact
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-ws/src /Users/lazy/Documents/agent-zero/rust/tests/ws_smoke.rs
git commit -m "feat: add websocket envelope and hub"
```

## Task 7: Add HTTP Models, Errors, And Routes

**Files:**
- Create: `rust/crates/a0-http/src/lib.rs`
- Create: `rust/crates/a0-http/src/router.rs`
- Create: `rust/crates/a0-http/src/handlers.rs`
- Create: `rust/crates/a0-http/src/error.rs`
- Create: `rust/crates/a0-http/src/models.rs`
- Create: `rust/crates/a0-http/src/middleware.rs`
- Test: `rust/tests/http_smoke.rs`

- [ ] **Step 1: Write the failing HTTP smoke tests**

```rust
#[tokio::test]
async fn health_route_returns_ok_true() {
    let app = a0_http::router::build_router(test_state());
    let response = app
        .oneshot(axum::http::Request::builder().uri("/health").body(axum::body::Body::empty()).unwrap())
        .await
        .unwrap();

    assert_eq!(response.status(), axum::http::StatusCode::OK);
}
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test http_smoke health_route_returns_ok_true -- --exact
```

Expected: FAIL because the router and handlers do not exist yet.

- [ ] **Step 3: Implement response models and HTTP error mapping**

```rust
use axum::{http::StatusCode, response::{IntoResponse, Response}, Json};
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct ErrorBody {
    pub ok: bool,
    pub error: ErrorDetail,
    pub request_id: String,
}

#[derive(Debug, Serialize)]
pub struct ErrorDetail {
    pub code: String,
    pub message: String,
}
```

- [ ] **Step 4: Implement the required handlers**

```rust
pub async fn health() -> Json<serde_json::Value> {
    Json(serde_json::json!({"ok": true, "status": "live"}))
}

pub async fn ready() -> Json<serde_json::Value> {
    Json(serde_json::json!({"ok": true, "status": "ready"}))
}

pub async fn version() -> Json<serde_json::Value> {
    Json(serde_json::json!({"ok": true, "version": env!("CARGO_PKG_VERSION")}))
}
```

Add placeholder `/api/message`, `/api/plugins`, and `/api/settings` handlers that return typed `not_implemented` bodies.

- [ ] **Step 5: Implement router construction**

```rust
use axum::{routing::{get, post}, Router};

pub fn build_router(state: AppState) -> Router {
    Router::new()
        .route("/health", get(handlers::health))
        .route("/ready", get(handlers::ready))
        .route("/version", get(handlers::version))
        .route("/api/message", post(handlers::api_message))
        .route("/api/plugins", get(handlers::api_plugins))
        .route("/api/settings", get(handlers::api_settings))
        .with_state(state)
}
```

- [ ] **Step 6: Run the HTTP smoke tests**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --test http_smoke -- --nocapture
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-http/src /Users/lazy/Documents/agent-zero/rust/tests/http_smoke.rs
git commit -m "feat: add http routes and stub responses"
```

## Task 8: Wire The Server Binary And App State

**Files:**
- Create: `rust/crates/a0-server/src/main.rs`
- Create: `rust/crates/a0-server/src/commands.rs`
- Create: `rust/crates/a0-server/src/bootstrap.rs`
- Create: `rust/crates/a0-server/src/state.rs`

- [ ] **Step 1: Write the failing server run check**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve --host 127.0.0.1 --port 60123
```

Expected: FAIL because the server binary sources do not exist yet.

- [ ] **Step 2: Implement `AppState` construction**

```rust
#[derive(Clone)]
pub struct AppState {
    pub settings: a0_config::Settings,
    pub health: a0_observability::HealthRegistry,
    pub ws_hub: a0_ws::WsHub,
    pub bridge: std::sync::Arc<dyn a0_core::BridgeService>,
}
```

- [ ] **Step 3: Implement CLI command execution**

```rust
pub async fn run(cli: a0_config::Cli) -> anyhow::Result<()> {
    let command = cli.command.clone();
    let settings = a0_config::load_settings_from_env(cli)?;

    match command {
        a0_config::Command::Serve => bootstrap::serve(settings).await,
        a0_config::Command::PrintConfig => {
            println!("{}", serde_json::to_string_pretty(&settings)?);
            Ok(())
        }
        a0_config::Command::Check => {
            println!("configuration valid");
            Ok(())
        }
    }
}
```

- [ ] **Step 4: Implement bootstrap and graceful shutdown**

```rust
pub async fn serve(settings: Settings) -> anyhow::Result<()> {
    let state = build_state(settings.clone());
    let app = a0_http::build_router(state);
    let listener = tokio::net::TcpListener::bind((settings.server.host.as_str(), settings.server.port)).await?;

    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            let _ = tokio::signal::ctrl_c().await;
        })
        .await?;

    Ok(())
}
```

- [ ] **Step 5: Run the server manually**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve --host 127.0.0.1 --port 60123
```

Expected: server starts and listens without crashing.

- [ ] **Step 6: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust/crates/a0-server/src
git commit -m "feat: wire rust server bootstrap"
```

## Task 9: Add Integration Docs And README Update

**Files:**
- Create: `docs/developer/rust-backend-skeleton.md`
- Modify: `README.md`

- [ ] **Step 1: Write the failing docs check**

Run:

```bash
test -f /Users/lazy/Documents/agent-zero/docs/developer/rust-backend-skeleton.md && echo present
```

Expected: no output because the file does not exist yet.

- [ ] **Step 2: Write the developer document**

```md
# Rust Backend Skeleton

This document describes the Rust backend skeleton under `rust/`, its crate layout, how to run it, and how it coexists with the current Python backend during migration.

## Run

```bash
cd rust
cargo run -p a0-server -- serve
```
```

Expand it with crate responsibilities, current limitations, and migration intent.

- [ ] **Step 3: Update `README.md` with a development note**

```md
### Rust backend skeleton

The repository includes an experimental Rust backend skeleton under `rust/`. It is a migration foundation and does not replace the current Python backend yet.
```

- [ ] **Step 4: Verify the docs exist**

Run:

```bash
test -f /Users/lazy/Documents/agent-zero/docs/developer/rust-backend-skeleton.md && echo present
```

Expected: `present`

- [ ] **Step 5: Commit**

```bash
git add /Users/lazy/Documents/agent-zero/docs/developer/rust-backend-skeleton.md /Users/lazy/Documents/agent-zero/README.md
git commit -m "docs: add rust backend skeleton guide"
```

## Task 10: Full Verification

**Files:**
- Verify: `rust/`
- Verify: `docs/developer/rust-backend-skeleton.md`
- Verify: `README.md`

- [ ] **Step 1: Run formatting**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo fmt --all
```

Expected: no diff from formatting or only intended formatting changes.

- [ ] **Step 2: Run all tests**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test
```

Expected: PASS

- [ ] **Step 3: Run a full compile check**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo check --workspace
```

Expected: PASS

- [ ] **Step 4: Manual smoke test**

Run:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve --host 127.0.0.1 --port 60123
curl -s http://127.0.0.1:60123/health
curl -s http://127.0.0.1:60123/ready
curl -s http://127.0.0.1:60123/version
```

Expected:

```json
{"ok":true,"status":"live"}
{"ok":true,"status":"ready"}
{"ok":true,"version":"0.1.0"}
```

- [ ] **Step 5: Final commit**

```bash
git add /Users/lazy/Documents/agent-zero/rust /Users/lazy/Documents/agent-zero/docs/developer/rust-backend-skeleton.md /Users/lazy/Documents/agent-zero/README.md
git commit -m "feat: add runnable rust backend skeleton"
```

## Self-Review

### Spec coverage

- Workspace/crate layout: Tasks 1, 3, 4, 5, 6, 7, 8
- Typed config and CLI precedence: Task 2
- HTTP liveness/readiness/version and stub APIs: Task 7
- WebSocket envelopes and request/reply basics: Task 6
- Observability and health: Task 4
- Null Python bridge: Task 5
- Migration documentation: Task 9
- Verification and acceptance criteria: Task 10

### Placeholder scan

- No `TODO`, `TBD`, or unresolved placeholders remain in the task steps.
- Every task lists concrete files, commands, and expected results.

### Type consistency

- `Settings`, `AppState`, `BridgeService`, and `HealthRegistry` names remain consistent across tasks.
- Public route names and crate names match the approved spec.

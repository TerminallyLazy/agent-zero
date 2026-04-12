# Rust Backend Skeleton Design

**Date:** 2026-04-12
**Topic:** Agent Zero backend migration, sub-project 1
**Status:** Approved

## Goal

Create a runnable Rust backend skeleton for Agent Zero that establishes the permanent architecture for a gradual Python-to-Rust migration. The skeleton must boot, serve stub HTTP and WebSocket endpoints, expose typed configuration and health/readiness state, and define clear internal service boundaries for later migration of the runtime, plugins, jobs, and tools.

This milestone is intentionally a foundation project, not a parity rewrite.

## Scope

### In scope

- Create a Rust workspace under `rust/`
- Provide a single bootable backend binary
- Add typed config loading with CLI, environment, file, and default layers
- Add structured logging and graceful shutdown
- Add real HTTP routes for liveness, readiness, and version/build metadata
- Add real WebSocket transport with structured event envelopes
- Define transport-independent service traits for future runtime migration
- Add a temporary Python-bridge boundary with a null implementation
- Add tests for config precedence, route behavior, WebSocket envelopes, and startup/shutdown

### Out of scope

- Feature parity with the current Python backend
- Porting agent execution, tools, prompts, memory, scheduler, or plugins
- Replacing the current Flask or Socket.IO runtime in production
- Cutting the current WebUI over to Rust in this milestone
- Implementing full auth and CSRF behavior

## Constraints

### Migration constraints

- The current backend is broad and intertwined: HTTP APIs, WebSocket routing, context/runtime orchestration, background jobs, plugin loading, and tool execution all currently live in Python.
- The first Rust milestone must avoid freezing the entire Python surface area into the new architecture.
- Future migration work needs stable seams so Python components can be bridged temporarily and replaced gradually.

### Domain constraints

- The backend must be async-first and avoid blocking handlers.
- Shared server state must be thread-safe.
- Config precedence must follow `CLI > env > file > defaults`.
- Errors must be explicit, typed, and machine-readable.
- Observability must be built in from the start.

## Architecture

Use a single-process async Rust server built on `tokio` and `axum`.

The Rust skeleton should stay operationally simple:

- one process
- one config model
- one tracing pipeline
- one graceful shutdown path
- one shared application state container

The transport layer must not become the system architecture. HTTP and WebSocket crates should depend on transport-independent traits in a core crate, not the other way around.

## Workspace Layout

```text
rust/
├── Cargo.toml
├── crates/
│   ├── a0-server/
│   ├── a0-http/
│   ├── a0-ws/
│   ├── a0-core/
│   ├── a0-config/
│   ├── a0-observability/
│   └── a0-bridge-py/
└── rustfmt.toml
```

### Crate responsibilities

#### `a0-server`

- binary crate
- startup wiring
- dependency composition
- listener bootstrap
- shutdown handling

#### `a0-http`

- route definitions
- request/response DTOs
- HTTP error mapping
- health, readiness, version, and placeholder API endpoints

#### `a0-ws`

- connection registry
- event envelope model
- correlation ID handling
- request/reply and broadcast primitives

#### `a0-core`

- domain types
- service traits
- shared error model
- no `axum` or transport-specific dependencies

#### `a0-config`

- typed configuration
- CLI argument parsing
- environment/file loading
- config validation

#### `a0-observability`

- tracing setup
- request IDs
- health registry primitives
- future metrics hooks

#### `a0-bridge-py`

- Python interoperability boundary
- null bridge implementation for milestone 1
- future process/RPC bridge implementations

## Core Service Boundaries

The initial architecture should define the permanent service boundaries even if the implementations are stubs.

### `ContextService`

Responsible for:

- context/session lookup
- context lifecycle operations
- future chat binding

### `AgentService`

Responsible for:

- future agent runtime orchestration
- task dispatch hooks
- runtime status reporting

### `PluginService`

Responsible for:

- plugin registry and discovery contract
- activation/config hooks
- future extension dispatch surface

### `JobService`

Responsible for:

- future scheduled/background jobs
- run state reporting

### `ToolService`

Responsible for:

- future tool registry and execution boundary

### `BridgeService`

Responsible for:

- temporary Python interop seam
- health reporting of bridge mode

### `HealthReporter`

Responsible for:

- liveness/readiness state
- component health snapshots

## Application State

The server should compose shared runtime state into a single `AppState` stored behind `Arc`.

`AppState` should contain:

- validated configuration
- `HealthService`
- `WsHub`
- concrete service trait objects
- build metadata
- shutdown token

Mutable shared state should be isolated to the components that require it, such as the WebSocket connection registry or health snapshots.

## HTTP Contract

Milestone 1 must provide real HTTP behavior for a small, stable contract surface.

### Required routes

- `GET /health`
- `GET /ready`
- `GET /version`
- `POST /api/message`
- `GET /api/plugins`
- `GET /api/settings`

### Route semantics

#### `GET /health`

- returns process liveness
- used for container/process health checks
- should remain green unless the process is fundamentally unhealthy

#### `GET /ready`

- returns dependency and component readiness
- includes component-level state such as bridge mode, config validity, and transport readiness
- can return non-ready while the process is still live

#### `GET /version`

- returns version/build metadata
- includes crate/app version and build commit when available

#### Placeholder `/api/*` routes

- return typed `"not_implemented"` responses
- use stable JSON envelopes
- do not pretend success

### Error envelope

All HTTP failures should map to a stable JSON structure:

```json
{
  "ok": false,
  "error": {
    "code": "not_implemented",
    "message": "The Rust backend route exists but is not implemented yet."
  },
  "request_id": "uuid"
}
```

## WebSocket Contract

Milestone 1 must include a real WebSocket transport with a stable envelope model.

### Initial capabilities

- accept connections
- assign/register connection IDs
- receive client events
- support request/reply with correlation IDs
- support server push and broadcast
- expose typed envelopes

### Envelope shape

```json
{
  "event": "state_push",
  "eventId": "uuid",
  "correlationId": "uuid-or-null",
  "handlerId": "rust.stub.health",
  "ts": "2026-04-12T12:34:56Z",
  "data": {}
}
```

### Initial event set

- `hello`
- `ping`
- `health_update`
- `state_request`
- `state_push`
- `not_implemented`

The envelope should preserve the high-value metadata model from the current Python system without copying the full Socket.IO implementation into Rust.

## Configuration And CLI

The server must use layered configuration with the following precedence:

1. CLI args
2. environment variables
3. config file
4. defaults

### Initial CLI

- `serve`
- `print-config`
- `check`

### Initial config domains

- HTTP host/port
- WebSocket path/bind settings
- log level and format
- origin allowlist
- auth mode
- CSRF mode
- bridge mode
- feature flags for placeholder routes

## Security Stance

Milestone 1 should establish security boundaries without pretending to fully port Python auth.

### Required now

- origin allowlist support
- request ID propagation
- connection/open close logging
- explicit auth mode config
- explicit CSRF mode config

### Deferred

- session validation parity
- CSRF token semantics parity
- production auth enforcement

The initial modes may include development or reserved behavior, but the boundary must be explicit in config and code.

## Python Bridge Strategy

The Rust architecture should be Rust-native first, with Python compatibility treated as a temporary seam.

### Bridge phases

1. `NullBridge`
2. `ProcessBridge`
3. `RpcBridge` if later justified
4. replacement by native Rust implementations

Milestone 1 only requires:

- bridge trait definitions
- null implementation
- config wiring
- health exposure

This keeps Python out of the core architecture while preserving a migration path for later phases.

## Error Handling

Use typed error mapping by boundary.

### Core layer

- domain errors as Rust enums
- no transport-specific status codes in core

### HTTP layer

- map domain errors to status codes
- always emit typed JSON error bodies

### WebSocket layer

- emit structured error events
- preserve correlation IDs when present

### Representative codes

- `not_implemented`
- `invalid_request`
- `unauthorized`
- `forbidden`
- `not_found`
- `timeout`
- `internal`

## Testing Strategy

Milestone 1 testing should focus on contracts and system boot behavior.

### Required tests

- config precedence tests
- route smoke tests
- HTTP error envelope tests
- WebSocket connection and `ping` tests
- WebSocket correlation/envelope tests
- liveness/readiness tests
- startup/shutdown integration test

### Not required in milestone 1

- performance benchmarking
- Python interop execution tests beyond null bridge wiring
- plugin behavior tests
- real agent runtime tests

## Implementation Order

1. Create the Rust workspace and crate skeleton
2. Add config, CLI, tracing, and build metadata
3. Add health/readiness primitives and server bootstrap
4. Add HTTP routes and typed error envelopes
5. Add WebSocket hub and event envelope model
6. Add core service traits and stub implementations
7. Add bridge crate and null bridge
8. Add tests
9. Add migration documentation for coexistence with Python

## Acceptance Criteria

This sub-project is complete when all of the following are true:

- `cargo run -p a0-server -- serve` starts successfully
- `/health`, `/ready`, and `/version` return valid JSON
- placeholder `/api/*` routes return explicit typed stub responses
- WebSocket clients can connect and receive structured replies to `ping`
- config precedence behaves correctly
- startup, request handling, WebSocket lifecycle, and shutdown are traced
- the crate boundaries allow future migration work without redesigning the transport layer

## Follow-On Work

After this milestone, migration should proceed incrementally rather than as a one-shot rewrite. Likely next sub-projects:

1. HTTP/API compatibility expansion
2. context/chat lifecycle migration
3. WebSocket state push migration
4. plugin registry and activation migration
5. Python bridge execution mode
6. native Rust replacements for bridge-backed services

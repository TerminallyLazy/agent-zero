# Rust Backend Skeleton

This document describes the experimental Rust backend skeleton under [rust](/Users/lazy/Documents/agent-zero/rust). It is the first migration milestone for moving Agent Zero backend responsibilities out of Python without attempting full parity in one step.

## Current Status

The Rust workspace is runnable and intentionally narrow:

- typed config with `CLI > env > file > defaults`
- a bootable `a0-server` binary
- `GET /health`, `GET /ready`, and `GET /version`
- working external API routes for `POST /api_message` and `GET|POST /api_log_get`
- placeholder `/api/message`, `/api/plugins`, and `/api/settings` routes for the in-progress internal API surface
- a real WebSocket endpoint at `/ws`
- structured event envelopes with `eventId`, `correlationId`, `handlerId`, `ts`, and `data`
- a null Python bridge and transport-independent core traits for future migration

What it is not:

- a replacement for the Python backend
- API-compatible with every existing Agent Zero endpoint
- a production auth or CSRF implementation

## Workspace Layout

```text
rust/
├── Cargo.toml
├── config/agent-zero.toml
└── crates/
    ├── a0-server/
    ├── a0-http/
    ├── a0-ws/
    ├── a0-core/
    ├── a0-config/
    ├── a0-observability/
    └── a0-bridge-py/
```

## Crate Responsibilities

- `a0-server`: CLI entrypoint, runtime bootstrap, graceful shutdown.
- `a0-http`: HTTP routes, WebSocket upgrade route, response envelopes, app state.
- `a0-ws`: WebSocket hub, envelope types, stub event handling.
- `a0-core`: domain errors, shared types, service traits.
- `a0-config`: CLI parsing and layered settings loading.
- `a0-observability`: tracing bootstrap and health/readiness registry.
- `a0-bridge-py`: null bridge now, Python interop seam later.

## Run

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve
```

Override config from the CLI:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve --host 127.0.0.1 --port 60123 --log-format json
```

Print the resolved config:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- print-config
```

Validate that config loading works:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- check
```

## Verify

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo test --workspace
cargo check --workspace
```

Manual smoke:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve --host 127.0.0.1 --port 60123
curl -s http://127.0.0.1:60123/health
curl -s http://127.0.0.1:60123/ready
curl -s http://127.0.0.1:60123/version
curl -s http://127.0.0.1:60123/api_log_get?context_id=<context-id>\&length=10
```

Create and continue a context:

```bash
curl -s http://127.0.0.1:60123/api_message \
  -H 'content-type: application/json' \
  -d '{"message":"hello from curl","project_name":"demo"}'

curl -s http://127.0.0.1:60123/api_message \
  -H 'content-type: application/json' \
  -d '{"context_id":"<context-id>","message":"follow-up"}'
```

WebSocket smoke:

```json
{"event":"ping","correlationId":"00000000-0000-0000-0000-000000000001","data":{"source":"manual"}}
```

Send that payload to `ws://127.0.0.1:60123/ws` and expect a `ping` envelope with `"message":"pong"`.

## Migration Intent

The Rust skeleton is designed so the transport layer does not become the full architecture. HTTP and WebSocket crates sit on top of transport-independent traits in `a0-core`, and the Python bridge is isolated to `a0-bridge-py`.

That lets future work proceed incrementally:

1. replace the in-memory conversation service with a bridge-backed runtime service
2. migrate more HTTP contract coverage
3. migrate WebSocket state push and broadcast flows
4. introduce a real Python bridge mode if needed
5. replace bridge-backed services with native Rust implementations

## Coexistence With Python

The current Python backend remains the real runtime. The Rust server is a migration foundation living beside it in the same repository. That means:

- Python remains the source of truth for production behavior
- Rust is safe to evolve without pretending parity exists yet
- contract decisions can be tested in isolation before cutover work starts

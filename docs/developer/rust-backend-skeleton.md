# Rust Backend Skeleton

This document describes the experimental Rust backend skeleton under [rust](/Users/lazy/Documents/agent-zero/rust). It is the first migration milestone for moving Agent Zero backend responsibilities out of Python without attempting full parity in one step.

If you want a direct install path instead of repo-local `cargo run` commands, use the step-by-step guide in [Rust Backend Install](rust-backend-install.md) and the installer at `rust/scripts/install-rust-backend.sh`.

## Current Status

The Rust workspace is runnable and intentionally narrow:

- typed config with `CLI > env > file > defaults`
- a bootable `a0-server` binary
- `GET /` plus static `webui/` asset serving for the real browser shell
- `GET /health`, `GET /ready`, and `GET /version`
- a basic UI bootstrap route at `GET /api/csrf_token`
- working UI transport routes for `POST /message` and `POST /message_async`
- working external API routes for `POST /api_message` and `GET|POST /api_log_get`
- working UI state routes for `POST /api/chat_create` and `POST /api/poll`
- placeholder `/api/message`, `/api/plugins`, and `/api/settings` routes for the in-progress internal API surface
- a real WebSocket endpoint at `/ws`
- structured event envelopes with `eventId`, `correlationId`, `handlerId`, `ts`, and `data`
- a null Python bridge and transport-independent core traits for future migration
- an `http` bridge mode that can delegate external API and UI state calls to a running Python backend

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

Quick install from this repository checkout:

```bash
bash rust/scripts/install-rust-backend.sh
```

See [Rust Backend Install](rust-backend-install.md) for the full workflow, installed paths, browser URL, and verification steps.

Fastest repo-local launch:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- serve
open http://127.0.0.1:50001/
```

Current limitation: the Rust server now fronts the real `webui/` shell and static files, but Socket.IO parity is still incomplete, so this is not yet a full Python-backend replacement.

Override config from the CLI:

```bash
cd /Users/lazy/Documents/agent-zero/rust
cargo run -p a0-server -- --host 127.0.0.1 --port 60123 --log-format json serve
```

Enable bridge mode with environment variables:

```bash
cd /Users/lazy/Documents/agent-zero/rust
A0_BRIDGE_MODE=http \
A0_BRIDGE_BASE_URL=http://127.0.0.1:50001 \
A0_BRIDGE_API_KEY=your-token \
cargo run -p a0-server -- serve
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
cargo run -p a0-server -- --host 127.0.0.1 --port 60123 serve
curl -s http://127.0.0.1:60123/health
curl -s http://127.0.0.1:60123/ready
curl -s http://127.0.0.1:60123/version
curl -s http://127.0.0.1:60123/api_log_get?context_id=<context-id>\&length=10
```

Bootstrap the current Web UI transport:

```bash
curl -s http://127.0.0.1:60123/api/csrf_token

curl -s http://127.0.0.1:60123/message_async \
  -H 'content-type: application/json' \
  -d '{"text":"hello from webui","context":null,"message_id":"demo-1"}'
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

Create a chat context and fetch a UI snapshot:

```bash
curl -s http://127.0.0.1:60123/api/chat_create \
  -H 'content-type: application/json' \
  -d '{"current_context":"<context-id>"}'

curl -s http://127.0.0.1:60123/api/poll \
  -H 'content-type: application/json' \
  -d '{"context":"<context-id>"}'
```

`/api/poll` accepts the same optional fields as the Python backend. Missing `log_from` and `notifications_from` default to `0`, and `timezone` may be omitted.

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
- bridge mode allows Rust to front selected API flows while delegating real work to Python

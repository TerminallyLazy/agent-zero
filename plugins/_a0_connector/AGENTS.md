# A0 Connector Plugin DOX

## Purpose

- Own the current Agent Zero connector plugin for HTTP and WebSocket integration.
- Provide remote execution, text-editing freshness, and connector runtime bridges.

## Ownership

- `plugin.yaml` owns plugin metadata and settings scope.
- `api/` owns connector WebSocket and API entry points.
- `helpers/` owns chat context, event bridge, execution config, freshness, version, and WebSocket runtime helpers.
- `tools/`, `prompts/`, `skills/`, `extensions/`, and `webui/` own connector-facing agent and UI contributions.

## Local Contracts

- Preserve session-auth and `auth.handlers` activation assumptions.
- Keep remote tool prompts synchronized with remote tool behavior and disclose
  them only from connected CLI metadata: no connected CLI hides all remote tool
  prompts, remote file metadata enables `text_editor_remote`, F4-enabled remote
  execution metadata enables `code_execution_remote`, and supported enabled
  Computer Use that does not need re-arming enables `computer_use_remote`.
- Never re-add a connector prompt that the effective project/profile tool policy
  blocks.
- Do not bypass WebSocket authentication or leak connector session data.
- `host_tasks_v1` adds native read-only per-chat status and explicit text-only
  host submission through authenticated, CSRF-protected `host_status` and
  `host_task`. Mobile clients never grant scopes or change browser configuration.
- `helpers/host_targets.py` owns session/context-bound generation tokens and
  durable chat bindings. Require one unambiguous Launcher connection; reject
  stale connections, scope/config changes and competing clients without fallback.
  Subordinate contexts inherit through `parent_context_id`; running or queued
  descendants prevent retargeting. Persist bindings before submission and retain
  their restrictions after restart, requiring fresh explicit review.
- Host routing generations track execution-capable connections. Chat-only
  WebSocket observers may reconnect without invalidating a host binding; an
  observer that begins advertising host tools becomes a competing target.
  Browser inventory and the negotiated content-helper checksum are observations,
  not target identity; helper initialization must not revoke an unchanged host.
- Every remote tool rechecks its bound target before dispatch. Computer captures
  publish bounded `computer_snapshot` metadata with context, capture ID, server
  path, source, time and host identity; a capture is not proof of action success.
- Advertise Launcher gateways additively through HTTP capability
  `launcher_gateway` and WebSocket feature `launcher_gateway_control`. Older
  ordinary CLI clients retain their existing protocol fields and behavior; do
  not provide a partial tools-only fallback when either feature is absent.
- A Launcher `connector_hello` carries a versioned gateway object with kind,
  stable ID, host label, and bounded status. Store it per authenticated socket,
  remove it on disconnect, and let context-bound CLI sockets retain routing
  priority. One unique Launcher gateway may be the global fallback. A duplicate
  socket with the same ID replaces stale state; distinct simultaneous IDs fail
  closed as Multiple hosts.
- `connector_gateway_control` and `connector_gateway_control_result` cover
  master state, complete scope replacement, and Disconnect
  (`emergency_disconnect` on the wire). Protected
  WebUI mutations require CSRF, await the matching acknowledgement, and return
  refreshed status. Apply acknowledged master and scope state to remote file
  and execution routing before resolving the control request; the follow-up
  `connector_hello` only reconciles metadata. Never let the WebUI select a host
  folder or personal browser profile.
- Launcher gateway scopes expose file reading and writing separately. File
  writing depends on reading, and Code execution depends on file writing. Keep
  older gateway declarations without `file_write` read/write compatible.
- Agent Zero WebUI exposes the read-only Connect your computer assistant and
  authenticated setup continuation, with shared guidance from `helpers/setup_help.json`.
  Host access settings, Disconnect/Reconnect, scope changes, and
  Computer Use approval belong only to attached or detached A0 Launcher chrome.
  Keep the authenticated gateway HTTP/WebSocket protocol available for the
  Launcher and connector runtime. The setup assistant never grants host access.
- `host_setup_v1` is chat-independent and CSRF protected. Its bounded status
  projection omits profiles, endpoints and paths. `helpers/host_setup.py` owns
  the private SQLite server identity and 10-minute owner-bound continuation
  codes. Codes are single-claim, rate limited, idempotent by request ID and grant
  no scopes. Original-device confirmation precedes separate local permission
  review. Unknown client requests are read back, never automatically replayed.
  Verification metadata expires after five minutes and requires current access;
  browser evidence covers a temporary page, computer evidence covers capture only.
- File operation results may arrive as chunked JSON/base64
  `connector_file_op_result` frames; resolve the pending file operation only
  after all chunks for the `op_id` are assembled.
- Host browser status metadata may advertise `available_browsers` entries with browser ids, labels, CDP endpoints, status, and enabled state; keep older CLI payloads without those fields compatible.
- Model preset definitions exposed through v1 are global; project arguments select scope but never create project-owned definitions. Model switcher state reports the effective main, utility, and embedding models and preserves embedding-change notifications.
- The protected v1 `agent_editor` route delegates to the bundled Agent Editor
  API and must not define another profile schema or write profile files itself.
- The protected v1 `agents_list` response uses the shared agent presentation
  catalog rather than applying connector-specific visibility rules.
- Computer Use receipts describe transport success unless the connector returns explicit effect evidence. Linux target-bound typing requires a verified active/focused `window_id`; window activation uses focus, never a press action on an application or window node. Do not retry an identical failed Computer Use call.
- Accepted WebSocket user-message replay metadata may include attachment basenames only; strip paths, query strings, fragments, and bytes before logging them in `kvps`.

- `host_viewer_v1` negotiates native live capture and takeover. `helpers/host_control.py`
  persists ownership and receipts, never viewer pixels or keystrokes. Close the
  gate before host acquire; all four host tool families enforce epochs before
  dispatch. Plugin intervention/tool hooks hold owner and descendants independently
  of ordinary pause; Return supplies a fresh observation without starting a new run.
  Expiry/restart/unknown results remain held. Keep authenticated CSRF-protected
  `api/v1/host_viewer.py` bounded and non-replaying. Frames use existing browser RPC
  result transport; scope changes remain Launcher-owned.

## Work Guidance

- Setup's fixed `a0-launcher://setup` link opens local guidance without a payload
  or grant. Always retain manual-code and install/update fallback; a timeout
  does not establish whether Launcher is installed.

- Coordinate connector runtime changes with API, tools, prompts, and WebUI viewer behavior together.

## Verification

- Run connector-specific tests or smoke-test HTTP and `/ws` integration when changing runtime behavior.
- Launcher gateway regression coverage lives in
  `tests/test_a0_connector_launcher_gateway.py`.
- Host targeting, session isolation, persistence, inheritance and revocation
  regressions live in `tests/test_a0_connector_host_tasks.py`.

## Child DOX Index

No child DOX files.

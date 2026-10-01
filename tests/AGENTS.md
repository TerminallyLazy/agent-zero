# Tests DOX

## Purpose

- Own pytest regression, security, integration, and contract tests.
- Keep tests focused on behavior that should remain stable across framework changes.

## Ownership

- Test files live directly under `tests/` and are named for the behavior or subsystem they cover.
- Shared fixtures should be added only when multiple tests need them.
- Runtime artifacts created during tests should use pytest temporary directories or existing isolated test helpers.

## Local Contracts

- Tests must not require real API keys, network-only services, private user data, or local `usr/` runtime state.
- Keep tests deterministic and isolated from existing chats, uploads, downloads, plugin state, and settings.
- Prefer exercising public helper/API contracts over fragile implementation details when practical.
- Security regression tests should assert the protected behavior directly.
- Host-task tests cover session/context token isolation, durable pre-submission
  binding, stale/reconnected/competing routes, descendant inheritance and active
  work, scope revocation, and unchanged ordinary unbound routing.
- Chat-only observer reconnects preserve host generations; advertising host
  tools from an observer must still invalidate the binding as a competing route.
- Launcher gateway tests must cover feature negotiation, authenticated and
  CSRF-protected control, acknowledgement timeout, identity lifecycle,
  context-bound CLI routing precedence, duplicate/multiple-host behavior,
  scope-driven availability, and emergency disconnect without a live host.

- `test_a0_host_viewer.py` covers durable holds, ownership isolation, duplicate
  receipts, final dispatch epochs and fresh-state intervention. Keep lease tests
  isolated from real connector sessions and user capture data.

## Work Guidance

- Add focused tests near the affected subsystem's existing tests.
- Use descriptive test names that state the regression or contract.
- Avoid broad sleeps or real-time dependencies; use monkeypatching or controlled clocks where possible.

## Verification

- `test_a0_host_setup.py` covers shared readiness, verification freshness,
  protected API policy, continuation identity/owner isolation, single-claim
  behavior, cancellation, expiry and rate limits in an isolated database.

- Run `pytest` for broad changes.
- Run `pytest tests/test_name.py` for narrow changes and mention any broader test gaps at closeout.

## Child DOX Index

No child DOX files.

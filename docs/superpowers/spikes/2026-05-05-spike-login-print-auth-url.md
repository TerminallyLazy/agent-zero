# Spike 0.8: `jcode login --print-auth-url --json` flag set

**Date:** 2026-05-05
**Spec ref:** §5.7, §11
**jcode version probed:** v0.11.10
**Status:** Resolved — both flags exist; full machine-readable login flow available

## Findings

✅ All flags from spec/plan exist on `jcode login`:

| Flag | Purpose |
|------|---------|
| `--print-auth-url` | Print script-friendly auth URL and persist temp login state for later completion |
| `--json` | Emit machine-readable JSON |
| `--callback-url <URL>` | Complete printed flow with full callback URL or query string |
| `--auth-code <CODE>` | Complete printed flow with provider-issued auth code |
| `--complete` | Resume pending scriptable login flow that doesn't need callback/code |
| `--no-browser` | Don't open browser (SSH/headless) |
| `--google-access-tier full|readonly` | Gmail/Google access tier for non-interactive flows |
| `-a, --account <LABEL>` | Account label for multi-account support |

## Recommended flow for plugin WebUI

Two-step pattern:

1. **Initiate:** `jcode login --provider <p> --print-auth-url --json --no-browser` → JSON
   contains `auth_url`, optional `user_code`. Plugin opens `auth_url` in user's browser.
2. **Complete:** User pastes callback URL into plugin UI. Plugin runs
   `jcode login --provider <p> --callback-url <pasted>`.

For Copilot device flow: `--print-auth-url --json` returns a `user_code` to display; user enters
code at GitHub URL; plugin polls with `jcode login --provider copilot --complete` until success.

## Plan impact

Task 11.3 (`api/login_provider.py`) is correctly designed against `--print-auth-url --json`.
**No changes needed.**

Add Task 11.3.A for the second-leg "complete login" endpoint:

```python
# api/complete_login.py
class CompleteLogin(ApiHandler):
    async def process(self, input: dict, request: Request) -> dict:
        provider = input["provider"]
        callback = input.get("callback_url")
        code = input.get("auth_code")
        bin_path = locate_jcode_binary()
        cmd = [bin_path, "login", "--provider", provider, "--json"]
        if callback:
            cmd += ["--callback-url", callback]
        elif code:
            cmd += ["--auth-code", code]
        else:
            cmd += ["--complete"]
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT)
        return json.loads(out)
```

# Rust Backend Install

This guide is the shortest path to a working local install of the experimental Rust backend.

## What It Installs

By default, the install script places files here:

- binary: `~/.local/bin/a0-server`
- web UI assets: `~/.local/share/agent-zero/rust/webui`
- live config: `~/.config/agent-zero/rust/agent-zero.toml`
- sample config: `~/.config/agent-zero/rust/agent-zero.example.toml`

The installed binary automatically discovers the default config path above. It also auto-discovers the installed `webui/` assets from the binary prefix, so `a0-server serve` can front the browser UI after install without depending on your current working directory. If you install the config somewhere else, run the binary with `--config /path/to/agent-zero.toml`.

Current limitation: the Rust backend now serves the real Agent Zero HTML shell and static assets, but Socket.IO parity is still incomplete. You can open the UI in a browser and exercise the migrated HTTP flows, but this is not yet a drop-in replacement for the full Python runtime.

## Step 1: Install Rust

Install the stable Rust toolchain if `cargo` is not already available:

```bash
curl https://sh.rustup.rs -sSf | sh
source "$HOME/.cargo/env"
```

Verify:

```bash
cargo --version
rustc --version
```

## Step 2: Run The Install Script

From the repository root:

```bash
bash rust/scripts/install-rust-backend.sh
```

That script:

- builds `a0-server` in release mode
- installs the binary into `~/.local/bin`
- installs the `webui/` assets into `~/.local/share/agent-zero/rust/webui`
- installs a sample config into `~/.config/agent-zero/rust`
- preserves an existing live config unless you pass `--force-config`

Optional flags:

```bash
bash rust/scripts/install-rust-backend.sh --prefix "$HOME/.local"
bash rust/scripts/install-rust-backend.sh --config-dir "$HOME/.config/agent-zero/rust"
bash rust/scripts/install-rust-backend.sh --force-config
bash rust/scripts/install-rust-backend.sh --debug
```

## Step 3: Add The Binary To PATH

If the script reports that `~/.local/bin` is not on `PATH`, add it to your shell profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Reload your shell, then verify:

```bash
a0-server --help
```

## Step 4: Verify The Installed Config

For the default install layout:

```bash
a0-server check
```

For a custom config directory:

```bash
a0-server --config /path/to/agent-zero.toml check
```

If you want to inspect the effective settings:

```bash
a0-server print-config
```

## Step 5: Start The Server

Default config path:

```bash
a0-server serve
```

Explicit config path:

```bash
a0-server --config /path/to/agent-zero.toml serve
```

Override host and port at launch time:

```bash
a0-server --host 127.0.0.1 --port 60123 serve
```

## Step 6: Open The Browser UI

Once the server is running, open:

```text
http://127.0.0.1:50001/
```

If you overrode the port, use that port instead.

## Step 7: Smoke Test The HTTP Surface

Once the server is running:

```bash
curl -s http://127.0.0.1:50001/health
curl -s http://127.0.0.1:50001/version
curl -s http://127.0.0.1:50001/ | head -20
curl -s http://127.0.0.1:50001/api/chat_create \
  -H 'content-type: application/json' \
  -d '{}'
```

## Bridge Mode

To route supported endpoints back to the Python backend:

```bash
A0_BRIDGE_MODE=http \
A0_BRIDGE_BASE_URL=http://127.0.0.1:50001 \
a0-server serve
```

## Reinstall Or Update

Re-run the same install script after pulling new changes:

```bash
git pull
bash rust/scripts/install-rust-backend.sh
```

Use `--force-config` only when you want to replace your live config with the current sample config.

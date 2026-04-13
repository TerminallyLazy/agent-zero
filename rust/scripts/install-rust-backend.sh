#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Install the Agent Zero Rust backend from this repository checkout.

Usage:
  bash rust/scripts/install-rust-backend.sh [options]

Options:
  --prefix DIR        Install prefix for the binary. Default: $HOME/.local
  --config-dir DIR    Install config directory. Default: ${XDG_CONFIG_HOME:-$HOME/.config}/agent-zero/rust
  --force-config      Overwrite the main config file with the sample config
  --debug             Build a debug binary instead of a release binary
  -h, --help          Show this help text
EOF
}

die() {
  printf 'error: %s\n' "$1" >&2
  exit 1
}

require_command() {
  local name="$1"
  if ! command -v "$name" >/dev/null 2>&1; then
    die "missing required command '$name'. Install Rust with https://rustup.rs/ first."
  fi
}

quote_cmd() {
  printf '%q ' "$@"
}

prefix="${HOME}/.local"
default_config_root="${XDG_CONFIG_HOME:-${HOME}/.config}"
config_dir="${default_config_root}/agent-zero/rust"
force_config=0
profile="release"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --prefix)
      [[ $# -ge 2 ]] || die "--prefix requires a value"
      prefix="$2"
      shift 2
      ;;
    --config-dir)
      [[ $# -ge 2 ]] || die "--config-dir requires a value"
      config_dir="$2"
      shift 2
      ;;
    --force-config)
      force_config=1
      shift
      ;;
    --debug)
      profile="debug"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "unknown argument '$1'"
      ;;
  esac
done

require_command cargo
require_command install

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
rust_dir="$(cd "${script_dir}/.." && pwd)"
repo_dir="$(cd "${rust_dir}/.." && pwd)"

source_config="${rust_dir}/config/agent-zero.toml"
source_webui_dir="${repo_dir}/webui"
[[ -f "${source_config}" ]] || die "missing sample config at ${source_config}"
[[ -d "${source_webui_dir}" ]] || die "missing web UI assets at ${source_webui_dir}"

build_args=(build --manifest-path "${rust_dir}/Cargo.toml" -p a0-server)
target_binary="${rust_dir}/target/${profile}/a0-server"
if [[ "${profile}" == "release" ]]; then
  build_args+=(--release)
fi

install_bin_dir="${prefix}/bin"
install_share_dir="${prefix}/share/agent-zero/rust"
installed_binary="${install_bin_dir}/a0-server"
installed_webui_dir="${install_share_dir}/webui"
config_path="${config_dir}/agent-zero.toml"
example_config_path="${config_dir}/agent-zero.example.toml"
default_config_path="${default_config_root}/agent-zero/rust/agent-zero.toml"

printf 'Building a0-server (%s)...\n' "${profile}"
cargo "${build_args[@]}"

mkdir -p "${install_bin_dir}" "${config_dir}" "${install_share_dir}"

printf 'Installing binary to %s\n' "${installed_binary}"
install -m 0755 "${target_binary}" "${installed_binary}"

printf 'Installing web UI assets to %s\n' "${installed_webui_dir}"
rm -rf "${installed_webui_dir}"
cp -R "${source_webui_dir}" "${installed_webui_dir}"

printf 'Installing sample config to %s\n' "${example_config_path}"
install -m 0644 "${source_config}" "${example_config_path}"

config_status="kept existing config"
if [[ ! -f "${config_path}" || "${force_config}" -eq 1 ]]; then
  install -m 0644 "${source_config}" "${config_path}"
  config_status="wrote config"
fi

check_cmd=("${installed_binary}" check)
run_cmd=("${installed_binary}" serve)
if [[ "${config_path}" != "${default_config_path}" ]]; then
  check_cmd=("${installed_binary}" --config "${config_path}" check)
  run_cmd=("${installed_binary}" --config "${config_path}" serve)
fi

cat <<EOF

Install complete.

Installed files:
  binary: ${installed_binary}
  webui: ${installed_webui_dir}
  config: ${config_path} (${config_status})
  sample: ${example_config_path}

Next steps:
  1. $(quote_cmd "${installed_binary}" --help)
  2. $(quote_cmd "${check_cmd[@]}")
  3. $(quote_cmd "${run_cmd[@]}")
  4. Open http://127.0.0.1:50001/ in your browser after the server starts
EOF

case ":${PATH}:" in
  *":${install_bin_dir}:"*) ;;
  *)
    cat <<EOF

PATH note:
  ${install_bin_dir} is not currently on PATH.
  Add this to your shell profile if you want to run 'a0-server' directly:
    export PATH="${install_bin_dir}:\$PATH"
EOF
    ;;
esac

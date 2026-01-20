#!/bin/bash
set -e

# activate venv
. "/ins/setup_venv.sh" "$@"

# install playwright if not installed (should be from requirements.txt)
uv pip install playwright

# set PW installation path to /a0/tmp/playwright
export PLAYWRIGHT_BROWSERS_PATH=/a0/tmp/playwright

# install chromium with dependencies
apt-get install -y fonts-unifont libnss3 libnspr4 libatk1.0-0 libatspi2.0-0 libxcomposite1 libxdamage1 libatk-bridge2.0-0 libcups2
playwright install chromium --only-shell

# ===== Agent Browser Installation =====
# Install Node.js 20 LTS (if not already installed)
if ! command -v node &> /dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
fi

# Install agent-browser globally
npm install -g agent-browser

# Install agent-browser's Chromium (or it will use Playwright's via --executable-path)
# Note: We set AGENT_BROWSER_EXECUTABLE_PATH in runtime to reuse Playwright's Chromium
agent-browser install || true  # May fail if chromium already exists, that's ok

# Note: Port 9223 is used for WebSocket streaming when headed mode is enabled
echo "Agent-browser installed. Streaming port: 9223"

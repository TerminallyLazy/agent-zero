#!/bin/bash
# Build the visual document service Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Copy the HTTP server to the build context
cp "$PROJECT_ROOT/python/helpers/visual_document_http_server.py" "$SCRIPT_DIR/server.py"

# Build the image
docker build -t agent0ai/visual-document-service:latest "$SCRIPT_DIR"

# Clean up copied file
rm -f "$SCRIPT_DIR/server.py"

echo "Build complete: agent0ai/visual-document-service:latest"

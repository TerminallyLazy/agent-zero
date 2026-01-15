#!/bin/bash
# Build the visual document service Docker image

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Copy the HTTP server to the build context
cp "$PROJECT_ROOT/python/helpers/visual_document_http_server.py" "$SCRIPT_DIR/server.py"

# Build the image (local tag - not pushed to registry)
docker build -t a0-visual-document-service:local "$SCRIPT_DIR"

# Clean up copied file
rm -f "$SCRIPT_DIR/server.py"

echo "Build complete: a0-visual-document-service:local"
echo "To use Docker sidecar mode, set visual_doc_execution_mode to 'docker_sidecar' in settings"

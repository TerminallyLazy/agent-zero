#!/usr/bin/env python3
"""
Standalone worker process for LitePali visual document processing.

Communicates via JSON-lines protocol over stdin/stdout.

Request format:
    {"action": "index", "uri": "...", "pdf_path": "...", "settings": {...}}
    {"action": "search", "query": "...", "document_uris": [...], "limit": 5}
    {"action": "status"}
    {"action": "shutdown"}

Response format:
    {"success": true, "result": ...}
    {"success": false, "error": "..."}
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


class VisualDocumentWorker:
    """Worker that handles LitePali operations in isolation."""

    def __init__(self):
        self._litepali = None
        self._indexed_docs: Dict[str, dict] = {}  # doc_hash -> metadata
        self._model_name: Optional[str] = None

    def _log(self, message: str) -> None:
        """Log to stderr (stdout is reserved for protocol)."""
        print(f"[worker] {message}", file=sys.stderr, flush=True)

    def _send_response(self, success: bool, result: Any = None, error: str = None) -> None:
        """Send JSON response to stdout."""
        response = {"success": success}
        if result is not None:
            response["result"] = result
        if error is not None:
            response["error"] = error
        print(json.dumps(response), flush=True)

    def _ensure_litepali(self, model_name: str = "vidore/colpali-v1.2") -> None:
        """Initialize LitePali if not already loaded or model changed."""
        if self._litepali is not None and self._model_name == model_name:
            return

        self._log(f"Loading LitePali model: {model_name}")

        try:
            from litepali import LitePali
        except ImportError as e:
            raise ImportError(
                "LitePali not installed. Run: pip install litepali colpali-engine"
            ) from e

        import torch
        device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"

        self._litepali = LitePali(model_name=model_name, device=device)
        self._model_name = model_name
        self._log(f"LitePali loaded on {device}")

    def handle_index(self, request: dict) -> dict:
        """Handle index request."""
        uri = request["uri"]
        pdf_path = request["pdf_path"]
        output_dir = Path(request["output_dir"])
        settings = request.get("settings", {})

        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        dpi = settings.get("pdf_dpi", 144)
        max_pages = settings.get("max_pages", 50)
        batch_size = settings.get("batch_size", 4)

        self._ensure_litepali(model_name)

        from litepali import ImageFile
        import pdf2image

        # Convert PDF to images
        self._log(f"Converting PDF to images: {pdf_path}")
        images_dir = output_dir / "images"
        os.makedirs(images_dir, exist_ok=True)

        images = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=1,
            last_page=max_pages
        )

        image_paths = []
        for i, image in enumerate(images):
            image_path = images_dir / f"page_{i+1:03d}.png"
            image.save(image_path, "PNG")
            image_paths.append(str(image_path))

        self._log(f"Converted {len(image_paths)} pages")

        # Index with LitePali
        import hashlib
        doc_hash = hashlib.sha256(uri.encode()).hexdigest()[:12]

        self._log("Processing images through vision model...")
        for i, img_path in enumerate(image_paths):
            self._litepali.add(ImageFile(
                path=img_path,
                document_id=doc_hash,
                page_id=str(i + 1),
                metadata={"uri": uri, "page": i + 1}
            ))

        self._litepali.process(batch_size=batch_size)

        self._indexed_docs[doc_hash] = {
            "uri": uri,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

        return {
            "doc_hash": doc_hash,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

    def handle_search(self, request: dict) -> List[dict]:
        """Handle search request."""
        query = request["query"]
        document_uris = request.get("document_uris")
        limit = request.get("limit", 5)
        settings = request.get("settings", {})

        model_name = settings.get("model_name", "vidore/colpali-v1.2")
        self._ensure_litepali(model_name)

        # Filter by document URIs if specified
        import hashlib
        doc_hashes = None
        if document_uris:
            doc_hashes = [
                hashlib.sha256(uri.encode()).hexdigest()[:12]
                for uri in document_uris
            ]

        results = self._litepali.search(query, k=limit * 2)

        matches = []
        for result in results:
            if doc_hashes and result.document_id not in doc_hashes:
                continue

            matches.append({
                "document_uri": result.metadata.get("uri", ""),
                "page_number": int(result.metadata.get("page", 0)),
                "score": float(result.score),
                "image_path": result.path
            })

            if len(matches) >= limit:
                break

        return matches

    def handle_status(self) -> dict:
        """Handle status request."""
        return {
            "model_loaded": self._litepali is not None,
            "model_name": self._model_name,
            "indexed_documents": len(self._indexed_docs),
            "documents": list(self._indexed_docs.keys())
        }

    def handle_request(self, request: dict) -> None:
        """Process a single request."""
        action = request.get("action")

        try:
            if action == "index":
                result = self.handle_index(request)
                self._send_response(True, result=result)

            elif action == "search":
                result = self.handle_search(request)
                self._send_response(True, result=result)

            elif action == "status":
                result = self.handle_status()
                self._send_response(True, result=result)

            elif action == "shutdown":
                self._send_response(True, result="shutting down")
                sys.exit(0)

            else:
                self._send_response(False, error=f"Unknown action: {action}")

        except Exception as e:
            self._log(f"Error handling {action}: {e}")
            self._send_response(False, error=str(e))

    def run(self) -> None:
        """Main loop - read JSON requests from stdin, write responses to stdout."""
        self._log("Worker started, waiting for requests...")

        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue

            try:
                request = json.loads(line)
                self.handle_request(request)
            except json.JSONDecodeError as e:
                self._send_response(False, error=f"Invalid JSON: {e}")


def main():
    """Entry point for worker process."""
    worker = VisualDocumentWorker()
    worker.run()


if __name__ == "__main__":
    main()

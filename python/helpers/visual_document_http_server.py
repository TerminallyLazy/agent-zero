#!/usr/bin/env python3
"""
HTTP server wrapper for LitePali visual document processing.

Provides REST API endpoints for Docker sidecar mode.

Endpoints:
    POST /index - Index a PDF document
    POST /search - Search indexed documents
    GET /status - Get worker status
    GET /health - Health check for Docker
    POST /shutdown - Gracefully shutdown the server
"""

import hashlib
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="[http-server] %(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr
)
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models
# ============================================================================

class IndexSettings(BaseModel):
    """Settings for PDF indexing."""
    model_name: str = Field(default="vidore/colpali-v1.2", description="LitePali model name")
    pdf_dpi: int = Field(default=144, ge=72, le=300, description="DPI for PDF rendering")
    max_pages: int = Field(default=50, ge=1, le=500, description="Maximum pages to index")
    batch_size: int = Field(default=4, ge=1, le=32, description="Batch size for processing")


class IndexRequest(BaseModel):
    """Request to index a PDF document."""
    uri: str = Field(..., description="Unique identifier for the document")
    pdf_path: str = Field(..., description="Path to the PDF file")
    output_dir: str = Field(..., description="Directory for output files")
    settings: Optional[IndexSettings] = Field(default=None, description="Indexing settings")


class IndexResponse(BaseModel):
    """Response from indexing a document."""
    success: bool
    doc_hash: Optional[str] = None
    page_count: Optional[int] = None
    image_paths: Optional[List[str]] = None
    error: Optional[str] = None


class SearchSettings(BaseModel):
    """Settings for search."""
    model_name: str = Field(default="vidore/colpali-v1.2", description="LitePali model name")


class SearchRequest(BaseModel):
    """Request to search indexed documents."""
    query: str = Field(..., min_length=1, description="Search query")
    document_uris: Optional[List[str]] = Field(default=None, description="Filter by document URIs")
    limit: int = Field(default=5, ge=1, le=100, description="Maximum results to return")
    settings: Optional[SearchSettings] = Field(default=None, description="Search settings")


class SearchResult(BaseModel):
    """Single search result."""
    document_uri: str
    page_number: int
    score: float
    image_path: str


class SearchResponse(BaseModel):
    """Response from search."""
    success: bool
    results: Optional[List[SearchResult]] = None
    error: Optional[str] = None


class StatusResponse(BaseModel):
    """Response from status endpoint."""
    success: bool
    model_loaded: bool
    model_name: Optional[str] = None
    indexed_documents: int
    documents: List[str]


class HealthResponse(BaseModel):
    """Response from health check."""
    status: str
    ready: bool


class ShutdownResponse(BaseModel):
    """Response from shutdown endpoint."""
    success: bool
    message: str


# ============================================================================
# LitePali State Manager (Singleton)
# ============================================================================

class LitePaliState:
    """Singleton state manager for LitePali model."""

    _instance: Optional["LitePaliState"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._litepali = None
        self._indexed_docs: Dict[str, dict] = {}
        self._model_name: Optional[str] = None
        self._initialized = True
        logger.info("LitePaliState initialized")

    def ensure_model(self, model_name: str = "vidore/colpali-v1.2") -> None:
        """Initialize LitePali if not already loaded or model changed."""
        if self._litepali is not None and self._model_name == model_name:
            return

        logger.info(f"Loading LitePali model: {model_name}")

        try:
            from litepali import LitePali
        except ImportError as e:
            raise ImportError(
                "LitePali not installed. Run: pip install litepali colpali-engine"
            ) from e

        import torch
        try:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        except Exception as e:
            logger.warning(f"Device detection failed, defaulting to CPU: {e}")
            device = "cpu"

        self._litepali = LitePali(model_name=model_name, device=device)
        self._model_name = model_name
        logger.info(f"LitePali loaded on {device}")

    @property
    def litepali(self):
        return self._litepali

    @property
    def model_name(self) -> Optional[str]:
        return self._model_name

    @property
    def indexed_docs(self) -> Dict[str, dict]:
        return self._indexed_docs

    @property
    def is_loaded(self) -> bool:
        return self._litepali is not None


# ============================================================================
# FastAPI Application
# ============================================================================

app = FastAPI(
    title="Visual Document HTTP Server",
    description="HTTP wrapper for LitePali visual document processing",
    version="1.0.0"
)

# Global state
state = LitePaliState()


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Docker."""
    return HealthResponse(
        status="healthy",
        ready=True
    )


@app.get("/status", response_model=StatusResponse)
async def get_status():
    """Get current worker status."""
    return StatusResponse(
        success=True,
        model_loaded=state.is_loaded,
        model_name=state.model_name,
        indexed_documents=len(state.indexed_docs),
        documents=list(state.indexed_docs.keys())
    )


@app.post("/index", response_model=IndexResponse)
async def index_document(request: IndexRequest):
    """Index a PDF document."""
    try:
        settings = request.settings or IndexSettings()

        # Ensure model is loaded
        state.ensure_model(settings.model_name)

        from litepali import ImageFile
        import pdf2image

        pdf_path = request.pdf_path
        output_dir = Path(request.output_dir)

        # Validate PDF exists
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=400, detail=f"PDF not found: {pdf_path}")

        # Convert PDF to images
        logger.info(f"Converting PDF to images: {pdf_path}")
        images_dir = output_dir / "images"
        os.makedirs(images_dir, exist_ok=True)

        images = pdf2image.convert_from_path(
            pdf_path,
            dpi=settings.pdf_dpi,
            first_page=1,
            last_page=settings.max_pages
        )

        image_paths = []
        for i, image in enumerate(images):
            image_path = images_dir / f"page_{i+1:03d}.png"
            image.save(image_path, "PNG")
            image_paths.append(str(image_path))

        logger.info(f"Converted {len(image_paths)} pages")

        # Index with LitePali
        doc_hash = hashlib.sha256(request.uri.encode()).hexdigest()[:12]

        logger.info("Processing images through vision model...")
        for i, img_path in enumerate(image_paths):
            state.litepali.add(ImageFile(
                path=img_path,
                document_id=doc_hash,
                page_id=str(i + 1),
                metadata={"uri": request.uri, "page": i + 1}
            ))

        state.litepali.process(batch_size=settings.batch_size)

        state.indexed_docs[doc_hash] = {
            "uri": request.uri,
            "page_count": len(image_paths),
            "image_paths": image_paths
        }

        return IndexResponse(
            success=True,
            doc_hash=doc_hash,
            page_count=len(image_paths),
            image_paths=image_paths
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error indexing document: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search", response_model=SearchResponse)
async def search_documents(request: SearchRequest):
    """Search indexed documents."""
    try:
        settings = request.settings or SearchSettings()

        # Ensure model is loaded
        state.ensure_model(settings.model_name)

        # Filter by document URIs if specified
        doc_hashes = None
        if request.document_uris:
            doc_hashes = [
                hashlib.sha256(uri.encode()).hexdigest()[:12]
                for uri in request.document_uris
            ]

        results = state.litepali.search(request.query, k=request.limit * 2)

        matches = []
        for result in results:
            if doc_hashes and result.document_id not in doc_hashes:
                continue

            # Safely access metadata with null check
            metadata = result.metadata if result.metadata else {}
            matches.append(SearchResult(
                document_uri=metadata.get("uri", ""),
                page_number=int(metadata.get("page", 0)),
                score=float(result.score),
                image_path=result.path
            ))

            if len(matches) >= request.limit:
                break

        return SearchResponse(success=True, results=matches)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/shutdown", response_model=ShutdownResponse)
async def shutdown():
    """Gracefully shutdown the server."""
    logger.info("Shutdown requested")

    # Use sys.exit in a background task to allow response to be sent first
    import asyncio

    async def delayed_shutdown():
        await asyncio.sleep(0.5)
        sys.exit(0)

    asyncio.create_task(delayed_shutdown())

    return ShutdownResponse(success=True, message="Server shutting down")


# ============================================================================
# Main Entry Point
# ============================================================================

def main():
    """Run the HTTP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Visual Document HTTP Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=9010, help="Port to bind to")
    parser.add_argument("--workers", type=int, default=1, help="Number of workers")
    args = parser.parse_args()

    logger.info(f"Starting HTTP server on {args.host}:{args.port}")

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info"
    )


if __name__ == "__main__":
    main()

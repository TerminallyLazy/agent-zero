"""
Enhanced DocumentQueryStore with MemOS integration.

This module provides MemOS-compatible document query functionality while maintaining
compatibility with Agent Zero's existing document processing patterns.
"""

import uuid
from typing import Dict, List, Any, Optional, Tuple
from urllib.parse import urlparse

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agent import Agent
from python.helpers.memory import Memory
from python.helpers.log import LogItem
from python.helpers.print_style import PrintStyle
from python.helpers.document_query import DocumentQueryStore, DocumentQueryHelper


class MemOSDocumentQueryStore(DocumentQueryStore):
    """
    Enhanced DocumentQueryStore that uses MemOS memory cubes for document storage.
    
    This class extends the original DocumentQueryStore to leverage MemOS capabilities
    while maintaining API compatibility with existing Agent Zero document workflows.
    """

    def __init__(self, agent: Agent):
        """Initialize a MemOS-enhanced DocumentQueryStore instance."""
        super().__init__(agent)
        self.memory_backend: Memory | None = None

    def init_vector_db(self):
        """Initialize the memory backend (either FAISS or MemOS based on configuration)."""
        # This will be initialized when needed through get_memory_backend()
        return None

    async def get_memory_backend(self):
        """Get or initialize the memory backend."""
        if not self.memory_backend:
            self.memory_backend = await Memory.get(self.agent)
        return self.memory_backend

    async def add_document(
        self, text: str, document_uri: str, metadata: dict | None = None
    ) -> tuple[bool, list[str]]:
        """
        Add a document to MemOS memory cubes with enhanced metadata.

        Args:
            text: The document text content
            document_uri: Unique identifier for the document
            metadata: Optional metadata dictionary

        Returns:
            Tuple of (success_flag, list_of_document_ids)
        """
        try:
            # Normalize the URI
            normalized_uri = self.normalize_uri(document_uri)

            # Get memory backend
            memory = await self.get_memory_backend()

            # Check if document already exists
            existing_chunks = await self._get_chunks_by_uri(normalized_uri)
            if existing_chunks:
                return False, []  # Document already exists

            # Chunk the document
            docs = self._chunk_document(text, normalized_uri, metadata)

            if not docs:
                return False, []

            # Store in memory backend with document area
            ids = []
            for doc in docs:
                # Enhance metadata for MemOS
                doc.metadata.update({
                    "area": Memory.Area.INSTRUMENTS.value,  # Use INSTRUMENTS area for documents
                    "document_type": "document_chunk",
                    "source_uri": normalized_uri,
                })
                
                doc_id = await memory.insert_text(doc.page_content, doc.metadata)
                ids.append(doc_id)

            return True, ids

        except Exception as e:
            PrintStyle.error(f"Error adding document to MemOS: {e}")
            return False, []

    async def delete_document_by_uri(self, document_uri: str) -> int:
        """
        Delete all chunks of a document identified by URI from MemOS.

        Args:
            document_uri: The URI of the document to delete

        Returns:
            Number of chunks deleted
        """
        try:
            # Normalize the URI
            normalized_uri = self.normalize_uri(document_uri)

            # Get memory backend
            memory = await self.get_memory_backend()

            # Find chunks by URI
            chunks = await self._get_chunks_by_uri(normalized_uri)
            
            if not chunks:
                return 0

            # Extract document IDs
            ids_to_delete = [chunk.metadata.get("id") for chunk in chunks if chunk.metadata.get("id")]
            
            if ids_to_delete:
                await memory.delete_documents_by_ids(ids_to_delete)

            return len(ids_to_delete)

        except Exception as e:
            PrintStyle.error(f"Error deleting document from MemOS: {e}")
            return 0

    async def _get_chunks_by_uri(self, normalized_uri: str) -> List[Document]:
        """Get all chunks for a specific document URI."""
        try:
            memory = await self.get_memory_backend()
            
            # Search for chunks with matching URI
            filter_str = f"source_uri == '{normalized_uri}' and document_type == 'document_chunk'"
            
            chunks = await memory.search_similarity_threshold(
                query=normalized_uri,  # Use URI as query
                limit=1000,  # High limit to get all chunks
                threshold=0.1,  # Low threshold to catch all matches
                filter=filter_str
            )
            
            return chunks

        except Exception as e:
            PrintStyle.error(f"Error retrieving chunks for URI {normalized_uri}: {e}")
            return []

    async def search_documents_by_similarity(
        self,
        query: str,
        limit: int = 5,
        threshold: float = 0.7,
        document_uris: list[str] | None = None,
    ) -> list[Document]:
        """
        Search document chunks by similarity using MemOS capabilities.

        Args:
            query: Search query text
            limit: Maximum number of results
            threshold: Similarity threshold (0.0 to 1.0)
            document_uris: Optional list of specific document URIs to search

        Returns:
            List of matching document chunks
        """
        try:
            memory = await self.get_memory_backend()

            # Build filter for document chunks
            filter_parts = ["document_type == 'document_chunk'"]
            
            if document_uris:
                # Normalize URIs and create filter
                normalized_uris = [self.normalize_uri(uri) for uri in document_uris]
                uri_filter = " or ".join([f"source_uri == '{uri}'" for uri in normalized_uris])
                filter_parts.append(f"({uri_filter})")

            filter_str = " and ".join(filter_parts)

            # Search using MemOS
            results = await memory.search_similarity_threshold(
                query=query,
                limit=limit,
                threshold=threshold,
                filter=filter_str
            )

            return results

        except Exception as e:
            PrintStyle.error(f"Error searching documents in MemOS: {e}")
            return []

    async def get_all_documents(self) -> dict[str, list[Document]]:
        """
        Get all documents organized by URI.

        Returns:
            Dictionary mapping URIs to their document chunks
        """
        try:
            memory = await self.get_memory_backend()

            # Get all document chunks
            all_chunks = await memory.search_similarity_threshold(
                query="*",  # Wildcard query
                limit=10000,  # High limit
                threshold=0.0,  # Very low threshold
                filter="document_type == 'document_chunk'"
            )

            # Organize by URI
            documents_by_uri = {}
            for chunk in all_chunks:
                uri = chunk.metadata.get("source_uri", "unknown")
                if uri not in documents_by_uri:
                    documents_by_uri[uri] = []
                documents_by_uri[uri].append(chunk)

            # Sort chunks by chunk_index for each URI
            for uri in documents_by_uri:
                documents_by_uri[uri].sort(
                    key=lambda x: x.metadata.get("chunk_index", 0)
                )

            return documents_by_uri

        except Exception as e:
            PrintStyle.error(f"Error retrieving all documents from MemOS: {e}")
            return {}

    def _chunk_document(
        self, text: str, document_uri: str, metadata: dict | None = None
    ) -> List[Document]:
        """
        Chunk a document into smaller pieces for storage.

        Args:
            text: Document text to chunk
            document_uri: URI of the source document  
            metadata: Additional metadata

        Returns:
            List of Document objects representing chunks
        """
        if not text.strip():
            return []

        # Initialize text splitter
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.DEFAULT_CHUNK_SIZE,
            chunk_overlap=self.DEFAULT_CHUNK_OVERLAP,
            length_function=len,
        )

        # Split the text
        chunk_texts = text_splitter.split_text(text)

        # Create Document objects
        documents = []
        total_chunks = len(chunk_texts)

        for i, chunk_text in enumerate(chunk_texts):
            # Prepare metadata
            chunk_metadata = {
                "document_uri": document_uri,
                "chunk_index": i,
                "total_chunks": total_chunks,
                **(metadata or {})
            }

            # Create Document
            doc = Document(
                page_content=chunk_text.strip(),
                metadata=chunk_metadata
            )
            documents.append(doc)

        return documents

    async def get_document_analytics(self) -> Dict[str, Any]:
        """
        Get analytics about stored documents in MemOS.

        Returns:
            Dictionary with document statistics and insights
        """
        try:
            memory = await self.get_memory_backend()

            # Get all document chunks
            all_chunks = await memory.search_similarity_threshold(
                query="*",
                limit=10000,
                threshold=0.0,
                filter="document_type == 'document_chunk'"
            )

            # Analyze documents
            documents_by_uri = {}
            total_chunks = len(all_chunks)
            total_text_length = 0

            for chunk in all_chunks:
                uri = chunk.metadata.get("source_uri", "unknown")
                if uri not in documents_by_uri:
                    documents_by_uri[uri] = {
                        "chunk_count": 0,
                        "total_length": 0,
                        "metadata": chunk.metadata
                    }
                
                documents_by_uri[uri]["chunk_count"] += 1
                documents_by_uri[uri]["total_length"] += len(chunk.page_content)
                total_text_length += len(chunk.page_content)

            # Calculate statistics
            analytics = {
                "total_documents": len(documents_by_uri),
                "total_chunks": total_chunks,
                "total_text_length": total_text_length,
                "average_chunks_per_document": total_chunks / len(documents_by_uri) if documents_by_uri else 0,
                "average_text_length_per_document": total_text_length / len(documents_by_uri) if documents_by_uri else 0,
                "documents_by_uri": documents_by_uri
            }

            # Check if using MemOS backend
            if hasattr(memory, 'client') and hasattr(memory.client, 'memory_cube_id'):
                analytics["memory_backend"] = "MemOS"
                analytics["memory_cube_id"] = memory.client.memory_cube_id
                analytics["user_id"] = memory.client.user_id
            else:
                analytics["memory_backend"] = "FAISS"

            return analytics

        except Exception as e:
            PrintStyle.error(f"Error generating document analytics: {e}")
            return {"error": str(e)}


class MemOSDocumentQueryHelper(DocumentQueryHelper):
    """
    Enhanced DocumentQueryHelper with MemOS-specific capabilities.
    """

    def __init__(self, agent: Agent):
        """Initialize with MemOS-enhanced document store."""
        super().__init__(agent)
        # Override the store with MemOS-enhanced version
        self.store = MemOSDocumentQueryStore.get(agent)

    async def get_document_summary(self, document_uri: str) -> str:
        """
        Generate a summary of a specific document using MemOS capabilities.

        Args:
            document_uri: URI of the document to summarize

        Returns:
            Summary text
        """
        try:
            # Get document chunks
            normalized_uri = self.store.normalize_uri(document_uri)
            chunks = await self.store._get_chunks_by_uri(normalized_uri)

            if not chunks:
                return f"No document found with URI: {document_uri}"

            # Combine chunks to reconstruct document
            full_text = "\n".join([chunk.page_content for chunk in chunks])

            # Use utility model to generate summary
            summary_prompt = f"""Please provide a concise summary of the following document:

Document URI: {document_uri}
Total chunks: {len(chunks)}

Content:
{full_text[:5000]}{'...' if len(full_text) > 5000 else ''}

Provide a summary that captures the key points and main topics covered."""

            summary = await self.agent.call_utility_model(
                system="You are a helpful assistant that creates concise document summaries.",
                message=summary_prompt
            )

            return summary

        except Exception as e:
            PrintStyle.error(f"Error generating document summary: {e}")
            return f"Error generating summary: {str(e)}"

    async def search_across_documents(
        self, 
        query: str, 
        document_type_filter: str = "", 
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Enhanced search across all documents with MemOS capabilities.

        Args:
            query: Search query
            document_type_filter: Optional filter by document type/extension
            limit: Maximum results

        Returns:
            List of search results with enhanced metadata
        """
        try:
            # Search documents
            results = await self.store.search_documents_by_similarity(
                query=query,
                limit=limit,
                threshold=0.3  # Lower threshold for broader search
            )

            # Enhanced result formatting
            enhanced_results = []
            for result in results:
                metadata = result.metadata
                
                enhanced_result = {
                    "content": result.page_content,
                    "source_uri": metadata.get("source_uri", "unknown"),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "total_chunks": metadata.get("total_chunks", 1),
                    "document_type": metadata.get("file_type", "unknown"),
                    "timestamp": metadata.get("timestamp", "unknown")
                }

                # Add MemOS-specific metadata if available
                if metadata.get("memory_cube"):
                    enhanced_result["memory_cube"] = metadata.get("memory_cube")

                enhanced_results.append(enhanced_result)

            return enhanced_results

        except Exception as e:
            PrintStyle.error(f"Error in enhanced document search: {e}")
            return []